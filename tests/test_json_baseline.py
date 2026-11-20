import json
import unittest
from pathlib import Path

from baselines.json_exact import predictions

ROOT = Path(__file__).resolve().parents[1]


class JsonExactTests(unittest.TestCase):
    def test_direct_gold_for_each_seed_query(self):
        dataset = json.loads((ROOT / "datasets/synthetic-v0/items.json").read_text(encoding="utf-8"))
        rows = list(predictions(dataset))
        expected = {}
        for item in dataset["items"]:
            polarities = {a["id"]: a["polarity"] for a in item["assertions"]}
            for q in item["queries"]:
                ids = [e["assertion_id"] for e in q["expect"]["evidence"] if "assertion_id" in e]
                expected[item["id"], q["id"]] = [
                    {"assertion_id": aid, "polarity": polarities[aid]} for aid in sorted(ids)
                ]
                del q["expect"]
            item["assertions"].reverse()
        self.assertEqual(rows, list(predictions(dataset)))
        self.assertEqual([(r["item_id"], r["query_id"]) for r in rows], list(expected))
        status = {(): "未知", ("negative",): "反对", ("positive",): "支持", ("negative", "positive"): "冲突"}
        for row in rows:
            key = (row["item_id"], row["query_id"])
            with self.subTest(key=key):
                evidence = expected[key]
                self.assertEqual(row["evidence"], evidence)
                self.assertEqual(row["status"], status[tuple(sorted({e["polarity"] for e in evidence}))])

    def test_unsupported_interval_data_rejected(self):
        with self.assertRaisesRegex(ValueError, "0.2"):
            list(predictions({"ir_version": "0.3", "items": []}))
