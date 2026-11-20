import copy
import json
import subprocess
import sys
from pathlib import Path
import unittest

from baselines.evaluate import score


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.item = {"id": "i", "assertions": [
            {"id": aid, "context": "one", "valid_at": day, "polarity": "positive"}
            for aid, day in [("a:x", None), ("a:y", None), ("a:other", "2026-11-19")]
        ], "queries": [{"id": "q", "query": {"context": "one", "valid_at": None},
                        "expect": {"status": "支持", "evidence": []}}]}
        self.data = {"items": [self.item]}
        self.row = {"item_id": "i", "query_id": "q", "status": "支持", "evidence": []}

    def test_shared_leaf_is_counted_once_and_paths_distinguish_rules(self):
        inner = {"assertion_id": "d:one", "derived_by": "first",
                 "premises": ["a:x", "a:y"]}
        outer = {"derived_by": "second", "premises": ["d:one", "a:x"],
                 "trace": [inner, {"assertion_id": "a:x"}]}
        self.item["queries"][0]["expect"]["evidence"] = [
            {"derived_by": "second", "premises": [{"derived_by": "first", "premises": ["a:x", "a:y"]}, "a:x"]}
        ]
        prediction = copy.deepcopy(outer)
        prediction["trace"][0]["derived_by"] = "wrong"
        self.row["evidence"] = [prediction]
        report = score(self.data, [self.row])
        self.assertEqual(report["leaves"]["matched"], 2)
        self.assertEqual(report["rule_paths"]["gold"], 3)
        self.assertEqual(report["rule_paths"]["matched"], 1)

    def test_command_compares_ncsc_with_three_baselines(self):
        root = Path(__file__).resolve().parents[1]
        dataset = root / "datasets/synthetic-v0/items.json"
        run = subprocess.run([sys.executable, "-X", "utf8", "-m", "baselines.evaluate", str(dataset)],
                             cwd=root, check=True, encoding="utf-8", capture_output=True)
        report = json.loads(run.stdout)
        self.assertEqual(set(report["baseline_reports"]), {"json_exact", "kg", "rule_engine"})
        ncsc = report["ncsc_report"]
        queries = [q for item in json.loads(dataset.read_text(encoding="utf-8"))["items"]
                   for q in item["queries"]]
        self.assertEqual(ncsc["queries"], len(queries))
        self.assertEqual(ncsc["correct"], len(queries))
        unknowns = sum(q["expect"]["status"] == "未知" for q in queries)
        self.assertEqual(ncsc["unknown_as_refuted"], {"count": 0, "eligible": unknowns, "rate": 0.0})
        self.assertEqual(ncsc["provenance_complete"]["rate"], 1.0)

    def test_invalid_branch_cannot_claim_hits(self):
        self.item["queries"][0]["expect"]["evidence"] = [{"assertion_id": "a:x"}]
        bad = [
            {"derived_by": "r", "premises": ["a:x", "a:other"]},
            {"derived_by": "r", "premises": ["a:x", "d:no-trace"]},
            {"assertion_id": "d:loop", "derived_by": "r", "premises": ["d:loop"],
             "trace": [{"assertion_id": "d:loop", "derived_by": "r", "premises": ["a:x"]}]},
            {"derived_by": "r", "premises": ["a:x"], "trace": [{"assertion_id": "a:y"}]},
        ]
        self.row["evidence"] = bad
        report = score(self.data, [self.row])
        self.assertEqual(report["invalid_predicted_evidence"], len(bad))
        self.assertEqual(report["leaves"]["matched"], 0)

    def test_unknown_errors_and_missing_predictions(self):
        self.item["queries"][0]["expect"]["status"] = "未知"
        self.row["status"] = "反对"
        report = score(self.data, [self.row])
        self.assertEqual(report["unknown_gold_predicted_known"], 1)
        self.assertEqual(report["confusion"]["未知"]["反对"], 1)
        self.assertEqual(report["unknown_as_refuted"], {"count": 1, "eligible": 1, "rate": 1.0})
        with self.assertRaises(ValueError):
            score(self.data, [])
        with self.assertRaises(ValueError):
            score(self.data, [self.row, self.row])


if __name__ == "__main__":
    unittest.main()
