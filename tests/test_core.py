import copy
import json
import unittest
from pathlib import Path

from ncsc.core import IRValidationError, KnowledgeBase


EXAMPLE = Path(__file__).parents[1] / "examples" / "project_state.json"


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_rule_derives_blocked_with_trace(self):
        result = KnowledgeBase(self.doc).query("c:task:release", "r:status:blocked", "c:value:true", "ctx:project-alpha", "2026-11-19")
        self.assertEqual("支持", result["status"])
        self.assertEqual("resource_unavailable_blocks_task", result["evidence"][0]["derived_by"])
        self.assertEqual(["a:release-requires-key", "a:key-unavailable"], result["evidence"][0]["premises"])

    def test_missing_is_unknown_not_negative(self):
        result = KnowledgeBase(self.doc).query("c:task:release", "r:status:blocked", "c:value:true", "ctx:other", "2026-11-19")
        self.assertEqual("未知", result["status"])

    def test_time_isolation(self):
        result = KnowledgeBase(self.doc).query("c:task:release", "r:status:blocked", "c:value:true", "ctx:project-alpha", "2026-11-20")
        self.assertEqual("未知", result["status"])

    def test_positive_and_negative_in_same_scope_conflict(self):
        negative = copy.deepcopy(self.doc["assertions"][0])
        negative.update({"id": "a:not-blocked", "roles": {"subject": "c:task:release", "relation": "r:status:blocked", "object": "c:value:true"}, "polarity": "negative"})
        self.doc["assertions"].append(negative)
        result = KnowledgeBase(self.doc).query("c:task:release", "r:status:blocked", "c:value:true", "ctx:project-alpha", "2026-11-19")
        self.assertEqual("冲突", result["status"])

    def test_negative_only_is_opposition(self):
        self.doc["assertions"] = [{**self.doc["assertions"][0], "id": "a:not-blocked", "roles": {"subject": "c:task:release", "relation": "r:status:blocked", "object": "c:value:true"}, "polarity": "negative"}]
        result = KnowledgeBase(self.doc).query("c:task:release", "r:status:blocked", "c:value:true", "ctx:project-alpha", "2026-11-19")
        self.assertEqual("反对", result["status"])

    def test_reported_cause_does_not_infer_verified_fact(self):
        self.doc["assertions"] = [self.doc["assertions"][2]]
        result = KnowledgeBase(self.doc).query("c:task:release", "r:status:blocked", "c:value:true", "ctx:project-alpha", "2026-11-19")
        self.assertEqual("未知", result["status"])

    def test_rejects_unknown_fields(self):
        self.doc["assertions"][0]["confidence"] = 0.9
        with self.assertRaises(IRValidationError):
            KnowledgeBase(self.doc)

    def test_rejects_dangling_concept(self):
        self.doc["assertions"][0]["roles"]["object"] = "c:missing"
        with self.assertRaises(IRValidationError):
            KnowledgeBase(self.doc)

    def test_rejects_unsupported_time_interval(self):
        self.doc["assertions"][0]["valid_at"] = {"from": "2026-11-19"}
        with self.assertRaises(IRValidationError):
            KnowledgeBase(self.doc)


if __name__ == "__main__":
    unittest.main()
