import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from annotation.trial import DATA, read, trial_metrics


class TrialMetricTests(unittest.TestCase):
    def setUp(self):
        self.registry = read(DATA / "registry.json")
        items = read(DATA / "items.json")["items"][:2]
        self.gold = {"ir_version": "0.2", "items": items}
        self.packet = [{"id": i["id"], "text": i["text"]} for i in items]
        self.a = [{k: copy.deepcopy(i[k]) for k in ("id", "assertions", "not_annotated")} for i in items]
        self.b = copy.deepcopy(self.a)

    def report(self, gold=None):
        return trial_metrics(self.packet, self.registry, self.a, self.b, gold)

    def test_scoped_dedup_and_optional_gold(self):
        claim = self.b[0]["assertions"][0]
        duplicate = dict(claim, id="a:other", sources=[self.registry["sources"][-1]])
        self.b[0]["assertions"].append(duplicate)
        self.b[1]["assertions"][0].pop("valid_at")
        self.b.reverse()
        result = self.report(self.gold)
        self.assertEqual(result["assertions_a_b"], {"left": 2, "right": 2, "matched": 1, "micro_f1": .5})
        self.assertEqual(result["assertions_a_gold"]["micro_f1"], 1)
        self.assertEqual(result["assertions_b_gold"]["micro_f1"], .5)
        self.assertIsNone(result["not_annotated_a_b"]["micro_f1"])
        self.assertIsNone(result["reported_cause_upgrades"]["count"])
        self.assertNotIn("assertions_a_gold", self.report())

    def test_notes_use_item_span_and_reason(self):
        note = {"span": "11月19日", "reason": "absence"}
        self.a[0]["not_annotated"] = [note, dict(note, detail="重复")]
        self.b[1]["not_annotated"] = [note]
        self.assertEqual(self.report()["not_annotated_a_b"]["micro_f1"], 0)
        self.b[1]["not_annotated"] = []
        self.b[0]["not_annotated"] = [dict(note, detail="其他说明")]
        self.assertEqual(self.report()["not_annotated_a_b"]["matched"], 1)
        self.b[0]["not_annotated"][0]["reason"] = "modality"
        self.assertEqual(self.report()["not_annotated_a_b"]["matched"], 0)

    def test_no_metrics_for_pending_or_mismatched_gold(self):
        for altered in (self.gold["items"][:-1], self.gold["items"] * 2,
                        [dict(i, text=i["text"] + "。") for i in self.gold["items"]]):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                self.report(dict(self.gold, items=altered))
        self.a[1].update(assertions=None, not_annotated=None)
        with self.assertRaisesRegex(ValueError, "未填写"):
            self.report()

    def test_cli_uses_explicit_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in (("packet", self.packet), ("registry", self.registry),
                                  ("annotator-a", self.a), ("annotator-b", self.b), ("gold", self.gold)):
                (root / (name + ".json")).write_text(json.dumps(content), encoding="utf-8")
            args = [sys.executable, "-X", "utf8", "-m", "annotation.trial", "metrics",
                    tmp, "--gold", str(root / "gold.json")]
            result = subprocess.run(args, capture_output=True, encoding="utf-8", check=True)
            self.assertEqual(json.loads(result.stdout)["assertions_b_gold"]["micro_f1"], 1)
