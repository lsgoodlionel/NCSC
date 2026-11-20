"""以分区内的三元组索引回答 synthetic-v0 查询。"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def predictions(dataset):
    if dataset["ir_version"] != "0.2":
        raise ValueError("KG 基线仅支持 IR 0.2")
    for item in dataset["items"]:
        # 每个条目独立建图；平行边保留各自的断言 ID 和极性。
        graphs = defaultdict(lambda: defaultdict(list))
        for assertion in item["assertions"]:
            if "valid_during" in assertion:
                raise ValueError("IR 0.2 不支持 valid_during")
            polarity = assertion["polarity"]
            if polarity not in ("positive", "negative"):
                raise ValueError(f"未知断言极性：{polarity}")
            roles = assertion["roles"]
            triple = (roles["subject"], roles["relation"], roles["object"])
            graph = graphs[assertion["context"], assertion.get("valid_at")]
            graph[triple].append((assertion["id"], polarity))

        for record in item["queries"]:
            query = record["query"]
            graph = graphs.get((query["context"], query["valid_at"]), {})
            triple = (query["subject"], query["relation"], query["object"])
            matches = sorted(graph.get(triple, []))
            polarities = {polarity for _, polarity in matches}
            if len(polarities) == 2:
                status = "冲突"
            elif "positive" in polarities:
                status = "支持"
            elif "negative" in polarities:
                status = "反对"
            else:
                status = "未知"
            yield {
                "item_id": item["id"],
                "query_id": record["id"],
                "status": status,
                "evidence": [{"assertion_id": aid, "polarity": p} for aid, p in matches],
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
