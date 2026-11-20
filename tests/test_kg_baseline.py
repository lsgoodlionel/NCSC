import json
import unittest
from pathlib import Path

from baselines import json_exact, kg

DATA = Path(__file__).resolve().parents[1] / "datasets/synthetic-v0/items.json"


class GraphBaselineTests(unittest.TestCase):
    def test_all_seed_queries_match_json_baseline(self):
        data = json.loads(DATA.read_text(encoding="utf-8"))
        expected = list(json_exact.predictions(data))
        for item in data["items"]:
            item["assertions"].reverse()
            for q in item["queries"]:
                del q["expect"]
        self.assertEqual(list(kg.predictions(data)), expected)

    def test_interval_is_not_an_undated_edge(self):
        data = json.loads(DATA.read_text(encoding="utf-8"))
        edge = data["items"][0]["assertions"][0]
        del edge["valid_at"]
        edge["valid_during"] = {"start": "2026-11-19"}
        with self.assertRaisesRegex(ValueError, "valid_during"):
            list(kg.predictions(data))
