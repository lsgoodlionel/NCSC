"""在 0.2 和 0.3 正式入口上逐问核对已有 0.2 种子金标。"""
from collections import Counter
import json

from ncsc import KnowledgeBase
from tests.datasets.test_synthetic_v0 import ITEMS, document, summarize


def main():
    counts = Counter()
    for item in ITEMS:
        for version in ("0.2", "0.3"):
            kb = KnowledgeBase(document(item, version))
            for record in item["queries"]:
                q = record["query"]
                result = kb.query(q["subject"], q["relation"], q["object"], q["context"], q["valid_at"])
                actual = (result["status"], summarize(result["evidence"]),
                          [entry["premises"] for entry in result["suppressed"]])
                gold = record["expect"]
                if actual != (gold["status"], gold["evidence"], gold["suppressed"]):
                    raise ValueError(f'{version} {item["id"]}/{record["id"]} 与金标不符')
                counts[version] += 1
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
