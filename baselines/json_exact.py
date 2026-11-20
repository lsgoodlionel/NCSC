"""对 synthetic-v0 的 IR 0.2 断言做逐条精确匹配。"""

import argparse
import json
from pathlib import Path

ROLES = ("subject", "relation", "object")
STATUS = {
    frozenset(): "未知",
    frozenset({"positive"}): "支持",
    frozenset({"negative"}): "反对",
    frozenset({"positive", "negative"}): "冲突",
}


def predictions(dataset):
    """按文件中的条目与查询顺序输出结果，条目间证据隔离。"""
    if dataset["ir_version"] != "0.2":
        raise ValueError("JSON 精确匹配基线仅支持 IR 0.2")
    for item in dataset["items"]:
        for record in item["queries"]:
            query = record["query"]
            roles = {key: query[key] for key in ROLES}
            evidence = []
            for assertion in item["assertions"]:
                if "valid_during" in assertion:
                    raise ValueError("IR 0.2 不支持 valid_during")
                if (assertion["context"] == query["context"]
                        and assertion.get("valid_at") == query["valid_at"]
                        and assertion["roles"] == roles):
                    evidence.append({"assertion_id": assertion["id"], "polarity": assertion["polarity"]})
            evidence.sort(key=lambda entry: entry["assertion_id"])
            yield {
                "item_id": item["id"],
                "query_id": record["id"],
                "status": STATUS[frozenset(e["polarity"] for e in evidence)],
                "evidence": evidence,
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items", type=Path, help="synthetic-v0 的 items.json 路径")
    args = parser.parse_args()
    try:
        dataset = json.loads(args.items.read_text(encoding="utf-8"))
        rows = list(predictions(dataset))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"无法读取基线数据：{exc}\n")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
