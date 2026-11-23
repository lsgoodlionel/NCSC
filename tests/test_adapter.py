import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from adapters.base import propose_ir


class AdapterTests(unittest.TestCase):
    def setUp(self):
        fixture = Path(__file__).parent / "contract/fixtures/0.2/valid/example-migrated.json"
        self.doc = json.loads(fixture.read_text(encoding="utf-8"))
        self.doc["assertions"] = self.doc["assertions"][:1]
        self.source = self.doc["assertions"][0]["sources"][0]
        self.text = self.source["description"]
        self.sources = {self.source["id"]: self.text}
        self.provider = Mock(return_value=self.doc)

    def run_candidate(self):
        return propose_ir(self.text, "0.2", sources=self.sources, provider=self.provider)

    def test_default_disabled(self):
        self.assertEqual(propose_ir(self.text, "0.2", sources=self.sources), {"status": "disabled"})

    def test_checked_candidate_is_independent(self):
        result = self.run_candidate()
        self.assertEqual(result["candidate"], self.doc)
        self.assertEqual(result["status"], "candidate")
        self.provider.assert_called_once_with(self.text, "0.2")
        self.doc["assertions"].clear()
        self.assertEqual(len(result["candidate"]["assertions"]), 1)

    def test_invalid_ir_rejected_without_retry(self):
        self.doc["assertions"][0]["roles"]["subject"] = "c:missing"
        self.assertEqual(self.run_candidate()["status"], "invalid_candidate")
        self.provider.assert_called_once()

    def test_ir03_calendar_and_empty_evidence(self):
        self.doc["version"] = "0.3"
        a = self.doc["assertions"][0]
        del a["valid_at"]
        a["valid_during"] = {"from": "2026-02-30"}
        def run():
            return propose_ir(self.text, "0.3", sources=self.sources, provider=self.provider)
        self.assertEqual(run()["status"], "invalid_candidate")
        a["valid_during"]["from"] = "2026-02-28"
        self.assertEqual(run()["candidate"], self.doc)
        self.doc["assertions"] = []
        self.assertEqual(run()["candidate"]["assertions"], [])

    def test_version_mismatch(self):
        self.doc["version"] = "0.1"
        self.assertEqual(self.run_candidate()["status"], "invalid_candidate")

    def test_source_cannot_be_invented_or_modified(self):
        for source in (dict(self.source, id="src:unknown"), dict(self.source, description="未经提供的陈述")):
            self.doc["assertions"][0]["sources"] = [source]
            self.assertEqual(self.run_candidate()["status"], "invalid_candidate")

    def test_source_must_appear_in_input(self):
        self.text = "另一份原文"
        self.assertEqual(self.run_candidate()["status"], "invalid_input")
        self.provider.assert_not_called()

    def test_provider_failure(self):
        self.provider.side_effect = RuntimeError("test failure")
        self.assertEqual(self.run_candidate()["status"], "provider_error")
        self.provider.assert_called_once()
