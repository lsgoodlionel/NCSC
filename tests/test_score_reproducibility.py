"""四系统评分的跨进程可复验性和未知误判口径。"""
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from baselines.evaluate import score


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets" / "synthetic-v0"


def run_cli(path, seed):
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "baselines.evaluate", str(path)],
        cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=str(seed)), check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    ).stdout


class ReproducibleScoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        folder = Path(temp.name)
        shutil.copyfile(DATA / "registry.json", folder / "registry.json")
        self.path = folder / "items.json"
        self.data = json.loads((DATA / "items.json").read_text(encoding="utf-8"))

    def write_data(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def test_full_report_is_identical_across_processes_and_input_orders(self):
        self.write_data()
        reference = run_cli(self.path, 0)
        for reverse in (False, True):
            if reverse:
                self.data["items"].reverse()
                for item in self.data["items"]:
                    item["assertions"].reverse()
                    item["queries"].reverse()
                self.write_data()
            for seed in (1, 2):
                with self.subTest(reverse=reverse, seed=seed):
                    self.assertEqual(run_cli(self.path, seed), reference)

    def test_missing_evidence_is_unknown_in_all_four_systems(self):
        item = self.data["items"][0]
        record = item["queries"][0]
        self.data["items"] = [item]
        item["assertions"] = []
        item["queries"] = [record]
        record["expect"] = {"status": "未知", "evidence": [], "suppressed": []}
        self.write_data()
        result = json.loads(run_cli(self.path, 0))
        self.assertEqual(set(result["baseline_reports"]), {"json_exact", "kg", "rule_engine"})
        for name, report in dict(result["baseline_reports"], ncsc=result["ncsc_report"]).items():
            with self.subTest(system=name):
                self.assertEqual(report["confusion"]["未知"], {"支持": 0, "反对": 0, "冲突": 0, "未知": 1})
                self.assertEqual(report["unknown_as_refuted"], {"count": 0, "eligible": 1, "rate": 0.0})
                self.assertEqual(report["provenance_complete"]["eligible"], 0)
                self.assertEqual(report["source_complete"], {"matched": 0, "eligible": 0, "rate": None})

    def test_injected_prediction_errors_preserve_unknown_denominators(self):
        # 只在内存中替换预测的状态；金标仍取自公开种子集。覆盖三个非未知类别。
        seen = Counter()
        actual = []
        for item in self.data["items"]:
            for q in item["queries"]:
                gold = q["expect"]["status"]
                seen[gold] += 1
                injected = gold
                if gold == "未知" and seen[gold] <= 3:
                    injected = ("支持", "反对", "冲突")[seen[gold] - 1]
                elif seen[gold] <= {"支持": 1, "反对": 2, "冲突": 1, "未知": 0}[gold]:
                    injected = "未知"
                actual.append({"item_id": item["id"], "query_id": q["id"],
                               "status": injected, "evidence": []})
        report = score(self.data, actual)
        total_unknown = seen["未知"]
        self.assertGreater(total_unknown, 3)
        self.assertEqual(report["unknown_as_refuted"],
                         {"count": 1, "eligible": total_unknown, "rate": 1 / total_unknown})
        self.assertEqual(report["known_gold_predicted_unknown"], 4)
        self.assertEqual(report["unknown_gold_predicted_known"], 3)
        for known, count in (("支持", 1), ("反对", 2), ("冲突", 1)):
            self.assertEqual(report["confusion"]["未知"][known], 1)
            self.assertEqual(report["confusion"][known]["未知"], count)
