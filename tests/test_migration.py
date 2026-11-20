import json
import unittest
from pathlib import Path

from ncsc.migration import preview_migration


ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "tests/contract/migration/0.1-to-0.2"


class MigrationTests(unittest.TestCase):
    def test_reference_candidate_and_report_are_byte_stable(self):
        source = "examples/project_state.json"
        raw = (ROOT / source).read_text(encoding="utf-8")
        doc = json.loads(raw)
        result = preview_migration(doc, source)
        for key, name in [("candidate", "project_state.0.2.json"), ("report", "project_state.report.json")]:
            rendered = json.dumps(result[key], ensure_ascii=False, indent=2) + "\n"
            self.assertEqual(rendered, (GOLD / name).read_text(encoding="utf-8"))
        self.assertEqual(doc, json.loads(raw))

    def test_unknown_kind_requires_decision(self):
        doc = {"version": "0.1", "assertions": [], "concepts": [{"kind": "临时", "aliases": ["甲"], "id": "c:x"}]}
        result = preview_migration(doc, "example")
        self.assertIsNone(result["report"]["needs_confirmation"][0]["proposed"])
        self.assertEqual(result["report"]["rejected"], [])
        self.assertEqual(result["report"]["output_status"], "candidate")

    def test_clean_and_unhandled_previews(self):
        doc = {"version": "0.1", "assertions": [], "concepts": [{"kind": "值", "aliases": ["甲"], "id": "c:x"}]}
        self.assertEqual(preview_migration(doc, "example")["report"]["output_status"], "final")
        doc["concepts"][0]["id"] = "c:X"
        report = preview_migration(doc, "example")["report"]
        self.assertEqual(report["output_status"], "candidate")
        self.assertIn("concepts[0].id", report["unhandled_first_error"])

    def test_pending_kinds_do_not_hide_independent_02_errors(self):
        doc = {"version": "0.1", "assertions": [], "concepts": [
            {"id": "r:p", "kind": "自定谓词", "aliases": ["谓词"]},
            {"id": "c:x", "kind": "自定类别", "aliases": ["事物"]},
            {"id": "c:y", "kind": "值", "aliases": ["重复", "重复"]},
        ]}
        result = preview_migration(doc, "mixed")
        self.assertIn("concepts[2].aliases", result["report"]["unhandled_first_error"])
        self.assertEqual(result["report"]["output_status"], "candidate")
        self.assertEqual(result["candidate"]["concepts"][:2], doc["concepts"][:2])
        self.assertEqual([entry["proposed"] for entry in
                          result["report"]["needs_confirmation"]], [None, None])

    def test_pending_target_kind_preserves_existing_02_error(self):
        doc = {"version": "0.1", "assertions": [], "concepts": [
            {"id": "c:x", "kind": "relation", "aliases": ["关系"]},
        ]}
        result = preview_migration(doc, "already-in-target-vocabulary")
        self.assertIn("concepts[0].id", result["report"]["unhandled_first_error"])
