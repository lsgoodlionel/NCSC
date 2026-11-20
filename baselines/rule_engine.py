"""IR 0.2 合成集的独立单跳规则基线，内置 R1。"""

import argparse
from collections import defaultdict
from itertools import product
import json
from pathlib import Path

from .json_exact import ROLES, STATUS

R1 = "resource_unavailable_blocks_task"


def _partition_facts(assertions):
    partitions = defaultdict(dict)
    for assertion in assertions:
        if "valid_during" in assertion:
            raise ValueError("IR 0.2 不支持 valid_during")
        partition = assertion["context"], assertion.get("valid_at")
        fact = tuple(assertion["roles"][key] for key in ROLES)
        polarities = partitions[partition].setdefault(fact, {})
        polarities.setdefault(assertion["polarity"], []).append(assertion["id"])
    return partitions


def _r1_proofs(subject, facts):
    """在本分区连接任务的资源需求与资源不可用断言，保留各组完整的叶子。"""
    premises = []
    for (task, relation, resource), need in facts.items():
        if (task, relation) != (subject, "r:task:requires") or set(need) != {"positive"}:
            continue
        unavailable = facts.get((resource, "r:resource:unavailable", "c:value:true"), {})
        if set(unavailable) == {"positive"}:
            premises.extend(product(need["positive"], unavailable["positive"]))
    return [{"derived_by": R1, "premises": list(pair), "polarity": "positive"}
            for pair in sorted(premises)]


def predictions(dataset):
    if dataset["ir_version"] != "0.2":
        raise ValueError("规则基线仅支持 IR 0.2")
    for item in dataset["items"]:
        partitions = _partition_facts(item["assertions"])
        for record in item["queries"]:
            query = record["query"]
            facts = partitions.get((query["context"], query["valid_at"]), {})
            subject, relation, obj = (query[key] for key in ROLES)
            direct = facts.get((subject, relation, obj), {})
            evidence = sorted(
                ({"assertion_id": aid, "polarity": polarity}
                 for polarity, ids in direct.items() for aid in ids),
                key=lambda e: e["assertion_id"],
            )
            if (relation, obj) == ("r:status:blocked", "c:value:true"):
                evidence.extend(_r1_proofs(subject, facts))
            yield {
                "item_id": item["id"], "query_id": record["id"],
                "status": STATUS[frozenset(e["polarity"] for e in evidence)],
                "evidence": evidence,
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items", type=Path, help="synthetic-v0 的 items.json 路径")
    args = parser.parse_args()
    try:
        rows = list(predictions(json.loads(args.items.read_text(encoding="utf-8"))))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"无法读取基线数据：{exc}\n")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
