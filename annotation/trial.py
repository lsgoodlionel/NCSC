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
            raise ValueError(f"{label} 仍有 {len(pending)} 个条目未填写，不能计算 κ")
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


def main():
    parser = argparse.ArgumentParser(description="生成独立试标盲包、校验单表或复核配对极性")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "check", "polarity"):
        command = commands.add_parser(name)
        command.add_argument("folder", type=Path)
        if name == "check":
            command.add_argument("sheet", choices=("a", "b"))
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
            result = polarity_agreement(packet, registry, read(folder / "annotator-a.json"),
                                        read(folder / "annotator-b.json"))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"试标工具：{exc}\n")


if __name__ == "__main__":
    main()
