"""在同一合成数据集上比较正式 NCSC 与三种基线。"""

import argparse
import json
from pathlib import Path

STATUSES = ("支持", "反对", "冲突", "未知")


def _walk(node, originals, ancestors, path, leaves, paths, gold):
    if not isinstance(node, dict):
        raise ValueError("证据节点须为对象")
    aid = node.get("assertion_id")
    if "derived_by" not in node:
        if aid not in originals or "trace" in node or "premises" in node:
            raise ValueError("无法在查询分区解析原始断言")
        if "polarity" in node and node["polarity"] != originals[aid]["polarity"]:
            raise ValueError("叶子极性与原始断言不符")
        leaves.add(aid)
        if path:
            paths.add((path, aid))
        return
    rule = node["derived_by"]
    premises = node.get("premises")
    if not isinstance(rule, str) or not rule or not isinstance(premises, list) or not premises:
        raise ValueError("推导缺少规则或前提")
    if aid is not None:
        if aid in originals or aid in ancestors:
            raise ValueError("推导 ID 冲突或路径成环")
        ancestors = ancestors | {aid}
    if node.get("polarity", "positive") != "positive":
        raise ValueError("0.2 规则只能推出正向证据")
    if gold and "trace" not in node:
        # 嵌套金标只记录规则及其有序前提，不需要生成生产证明 ID。
        children = [p if isinstance(p, dict) else {"assertion_id": p} for p in premises]
        for position, child in enumerate(children):
            _walk(child, originals, ancestors, path + ((rule, position),), leaves, paths, gold)
        return
    children = node.get("trace", [{"assertion_id": pid} for pid in premises])
    if not isinstance(children, list) or len(children) != len(premises):
        raise ValueError("规则前提和可展开的节点数量不符")
    for position, (pid, child) in enumerate(zip(premises, children)):
        if not isinstance(pid, str) or not isinstance(child, dict) or child.get("assertion_id") != pid:
            raise ValueError("规则前提与 trace 顺序或引用不符")
        _walk(child, originals, ancestors, path + ((rule, position),), leaves, paths, gold)


def _evidence(entries, originals, gold=False):
    leaves, paths, invalid = set(), set(), 0
    if not isinstance(entries, list):
        raise ValueError("evidence 须为列表")
    for node in entries:
        local_leaves, local_paths = set(), set()
        try:
            _walk(node, originals, set(), (), local_leaves, local_paths, gold)
        except (ValueError, TypeError, RecursionError):
            invalid += 1
        else:
            leaves.update(local_leaves)
            paths.update(local_paths)
    return leaves, paths, invalid


def _counts():
    return dict(gold=0, predicted=0, matched=0)


def _add_counts(target, gold, predicted):
    target["gold"] += len(gold)
    target["predicted"] += len(predicted)
    target["matched"] += len(gold & predicted)


def _ratio(matched, total):
    return matched / total if total else None


def score(dataset, predictions):
    """按 (item_id, query_id) 比较每个查询的四值状态与分区内解释。"""
    queries = {}
    for item in dataset["items"]:
        partitions = {}
        ids = set()
        for assertion in item["assertions"]:
            aid = assertion["id"]
            if aid in ids or "valid_during" in assertion:
                raise ValueError("仅支持条目内 ID 唯一的 0.2 单日断言")
            ids.add(aid)
            key = (assertion["context"], assertion.get("valid_at"))
            partitions.setdefault(key, {})[aid] = assertion
        for record in item["queries"]:
            key = (item["id"], record["id"])
            if key in queries:
                raise ValueError(f"金标查询重复：{key}")
            q = record["query"]
            queries[key] = record["expect"], partitions.get((q["context"], q["valid_at"]), {})

    matrix = {status: dict.fromkeys(STATUSES, 0) for status in STATUSES}
    leaf_counts, path_counts = _counts(), _counts()
    eligible = complete = invalid_count = 0
    for row in predictions:
        key = (row["item_id"], row["query_id"])
        if key not in queries:
            raise ValueError(f"预测查询未登记或重复：{key}")
        expect, originals = queries.pop(key)
        gold_status, status = expect["status"], row["status"]
        if gold_status not in STATUSES or status not in STATUSES:
            raise ValueError(f"状态超出四值集合：{key}")
        matrix[gold_status][status] += 1
        gold_leaves, gold_paths, invalid_gold = _evidence(expect["evidence"], originals, gold=True)
        if invalid_gold:
            raise ValueError(f"金标引用未解析、跨分区或成环：{key}")
        leaves, paths, invalid = _evidence(row["evidence"], originals)
        invalid_count += invalid
        _add_counts(leaf_counts, gold_leaves, leaves)
        _add_counts(path_counts, gold_paths, paths)
        if gold_leaves:
            eligible += 1
            complete += leaves == gold_leaves and paths == gold_paths and not invalid
    if queries:
        raise ValueError(f"缺少预测：{sorted(queries)}")
    for counts in (leaf_counts, path_counts):
        counts["precision"] = _ratio(counts["matched"], counts["predicted"])
        counts["recall"] = _ratio(counts["matched"], counts["gold"])
    total = sum(sum(row.values()) for row in matrix.values())
    correct = sum(matrix[status][status] for status in STATUSES)
    unknowns = sum(matrix["未知"].values())
    refuted = matrix["未知"]["反对"]
    return {
        "queries": total, "correct": correct, "accuracy": _ratio(correct, total),
        "confusion": matrix,
        "unknown_as_refuted": {"count": refuted, "eligible": unknowns, "rate": _ratio(refuted, unknowns)},
        "unknown_gold_predicted_known": sum(matrix["未知"][s] for s in STATUSES if s != "未知"),
        "known_gold_predicted_unknown": sum(matrix[s]["未知"] for s in STATUSES if s != "未知"),
        "leaves": leaf_counts, "rule_paths": path_counts,
        "invalid_predicted_evidence": invalid_count,
        "provenance_complete": {"matched": complete, "eligible": eligible, "rate": _ratio(complete, eligible)},
    }


def ncsc_predictions(dataset, registry):
    from ncsc import KnowledgeBase

    if dataset["ir_version"] != "0.2" or registry["ir_version"] != "0.2":
        raise ValueError("正式系统的评分入口只接受 IR 0.2 数据集与登记表")
    if dataset["dataset"] != registry["dataset"]:
        raise ValueError("登记表与查询数据不属于同一数据集")
    for item in dataset["items"]:
        kb = KnowledgeBase({"version": "0.2", "concepts": registry["concepts"], "assertions": item["assertions"]})
        for record in item["queries"]:
            q = record["query"]
            answer = kb.query(q["subject"], q["relation"], q["object"], q["context"], q["valid_at"])
            yield {"item_id": item["id"], "query_id": record["id"],
                   "status": answer["status"], "evidence": answer["evidence"]}


def main():
    from . import json_exact, kg, rule_engine

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items", type=Path, help="synthetic-v0 的 items.json 路径")
    args = parser.parse_args()
    try:
        dataset = json.loads(args.items.read_text(encoding="utf-8"))
        registry = json.loads(args.items.with_name("registry.json").read_text(encoding="utf-8"))
        ncsc_report = score(dataset, ncsc_predictions(dataset, registry))
        systems = {"json_exact": json_exact, "kg": kg, "rule_engine": rule_engine}
        reports = {name: score(dataset, module.predictions(dataset)) for name, module in systems.items()}
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"评分输入错误：{exc}\n")
    print(json.dumps({"dataset": dataset["dataset"], "baseline_reports": reports, "ncsc_report": ncsc_report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
