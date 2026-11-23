"""从仓库根目录运行 python3 -m annotation.trial --help。"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from ncsc.core import validate_document

DATA = Path(__file__).resolve().parents[1] / "datasets" / "synthetic-v0"
POLARITIES = ("positive", "negative")
REASONS = ("absence", "modality", "no-relation", "ambiguous")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def prepare(folder):
    items = read(DATA / "items.json")["items"]
    packet = [{"id": item["id"], "text": item["text"]} for item in items]
    sheet = [{"id": item["id"], "assertions": None, "not_annotated": None} for item in packet]
    registry = read(DATA / "registry.json")
    folder.mkdir(parents=True, exist_ok=False)
    for name, value in (("packet", packet), ("registry", registry),
                        ("annotator-a", sheet), ("annotator-b", sheet)):
        (folder / (name + ".json")).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def validate_sheet(packet, registry, sheet):
    texts = {item["id"]: item["text"] for item in packet}
    if not texts or len(texts) != len(packet):
        raise ValueError("盲包为空或存在重复条目")
    if not isinstance(sheet, list):
        raise ValueError("标注表必须为条目数组")
    seen = set()
    pending = []
    contexts = {ctx["id"] for ctx in registry["contexts"]}
    sources = {src["id"]: src["description"] for src in registry["sources"]}
    for row in sheet:
        if not isinstance(row, dict) or set(row) != {"id", "assertions", "not_annotated"}:
            raise ValueError("标注条目需要 id、assertions、not_annotated")
        item = row["id"]
        if not isinstance(item, str) or item not in texts or item in seen:
            raise ValueError(f"未知或重复条目 {item!r}")
        seen.add(item)
        assertions, notes = row["assertions"], row["not_annotated"]
        if assertions is None and notes is None:
            pending.append(item)
            continue
        if not isinstance(assertions, list) or not isinstance(notes, list):
            raise ValueError(f"{item} 两个答案栏须同时填写数组")
        validate_document({"version": "0.2", "concepts": registry["concepts"], "assertions": assertions})
        for claim in assertions:
            if claim["context"] not in contexts or any(
                sources.get(src["id"]) != src["description"] for src in claim["sources"]
            ):
                raise ValueError(f"{item} 上下文或来源不符合登记表")
        for note in notes:
            if not isinstance(note, dict) or set(note) - {"span", "reason", "detail"}:
                raise ValueError(f"{item} 未标注说明的格式错误")
            span = note.get("span")
            if (not isinstance(span, str) or not span.strip() or span not in texts[item]
                    or note.get("reason") not in REASONS or not isinstance(note.get("detail", ""), str)):
                raise ValueError(f"{item} 未标注的片段或原因无效")
    if seen != set(texts):
        raise ValueError(f"缺失条目 {sorted(set(texts) - seen)}")
    return pending


def polarity_keys(sheet):
    keys = defaultdict(set)
    for row in sheet:
        for claim in row["assertions"]:
            roles = claim["roles"]
            key = (row["id"], roles["subject"], roles["relation"], roles["object"],
                   claim["context"], claim.get("valid_at"))
            keys[key].add(claim["polarity"])
    return keys


def polarity_agreement(packet, registry, sheet_a, sheet_b):
    for label, sheet in (("A", sheet_a), ("B", sheet_b)):
        pending = validate_sheet(packet, registry, sheet)
        if pending:
            raise ValueError(f"{label} 仍有 {len(pending)} 个条目未填写，不能计算一致性")
    a, b = polarity_keys(sheet_a), polarity_keys(sheet_b)
    shared = a.keys() & b.keys()
    table = {i: {j: 0 for j in POLARITIES} for i in POLARITIES}
    ambiguous = 0
    for key in shared:
        if len(a[key]) != 1 or len(b[key]) != 1:
            ambiguous += 1
        else:
            table[next(iter(a[key]))][next(iter(b[key]))] += 1
    n = len(shared) - ambiguous
    report = {"shared_keys": len(shared), "single_label_pairs": n, "multi_label_keys": ambiguous,
              "a_only_keys": len(a.keys() - b.keys()), "b_only_keys": len(b.keys() - a.keys()),
              "confusion_a_by_b": table, "kappa": None}
    if ambiguous:
        report["reason"] = "multi_label_policy_required"
    elif not n:
        report["reason"] = "no_shared_pairs"
    else:
        observed = n * sum(table[p][p] for p in POLARITIES)
        expected = sum(sum(table[p].values()) * sum(table[q][p] for q in POLARITIES) for p in POLARITIES)
        if expected == n * n:
            report["reason"] = "constant_marginals"
        else:
            report["kappa"] = (observed - expected) / (n * n - expected)
    return report


def _assertions(sheet):
    return {(*key, polarity) for key, values in polarity_keys(sheet).items() for polarity in values}


def _notes(sheet):
    return {(row["id"], note["span"], note["reason"]) for row in sheet for note in row["not_annotated"]}


def _micro_f1(left, right):
    matched = len(left & right)
    total = len(left) + len(right)
    report = {"left": len(left), "right": len(right), "matched": matched,
              "micro_f1": 2 * matched / total if total else None}
    if not total:
        report["reason"] = "both_sets_empty"
    return report


def trial_metrics(packet, registry, sheet_a, sheet_b, gold=None):
    polarity = polarity_agreement(packet, registry, sheet_a, sheet_b)
    a, b = _assertions(sheet_a), _assertions(sheet_b)
    result = {"items": len(packet), "assertions_a_b": _micro_f1(a, b),
              "not_annotated_a_b": _micro_f1(_notes(sheet_a), _notes(sheet_b)), "polarity": polarity,
              "reported_cause_upgrades": {"count": None, "status": "requires_adjudication"}}
    if gold is not None:
        if not isinstance(gold, dict) or gold.get("ir_version") != "0.2" or not isinstance(gold.get("items"), list):
            raise ValueError("金标须为本轮 IR 0.2 条目集")
        items = gold["items"]
        texts = {item["id"]: item["text"] for item in items}
        if len(items) != len(texts) or texts != {item["id"]: item["text"] for item in packet}:
            raise ValueError("金标条目 ID 与文本须逐一匹配盲包")
        sheet = [{key: item[key] for key in ("id", "assertions", "not_annotated")} for item in items]
        if validate_sheet(packet, registry, sheet):
            raise ValueError("金标中存在未完成条目")
        reference = _assertions(sheet)
        result["assertions_a_gold"] = _micro_f1(a, reference)
        result["assertions_b_gold"] = _micro_f1(b, reference)
    return result


def main():
    parser = argparse.ArgumentParser(description="生成独立试标盲包、校验单表或复核配对指标")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "check", "polarity", "metrics"):
        command = commands.add_parser(name)
        command.add_argument("folder", type=Path)
        if name == "check":
            command.add_argument("sheet", choices=("a", "b"))
        if name == "metrics":
            command.add_argument("--gold", type=Path, help="人工核对过的本轮 IR 0.2 条目文件")
    args = parser.parse_args()
    folder = args.folder
    try:
        if args.command == "prepare":
            prepare(folder)
            return
        packet, registry = read(folder / "packet.json"), read(folder / "registry.json")
        if args.command == "check":
            pending = validate_sheet(packet, registry, read(folder / f"annotator-{args.sheet}.json"))
            result = {"items": len(packet), "pending": pending}
        else:
            a, b = (read(folder / f"annotator-{label}.json") for label in ("a", "b"))
            if args.command == "metrics":
                gold = read(args.gold) if args.gold else None
                if args.gold and gold is None:
                    raise ValueError("指定的金标文件为空值")
                result = trial_metrics(packet, registry, a, b, gold)
            else:
                result = polarity_agreement(packet, registry, a, b)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"试标工具：{exc}\n")


if __name__ == "__main__":
    main()
