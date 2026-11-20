"""通过真实 IR 加载入口检验 0.1 初始白名单。"""

import json
import unittest
from unittest.mock import patch
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from ncsc import KnowledgeBase

EXAMPLE = Path(__file__).parents[1] / "examples" / "project_state.json"


class InitialRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.need, self.lack, self.report = self.doc["assertions"]

    def query(self, valid_at: Optional[str] = "2026-11-19") -> dict[str, Any]:
        return KnowledgeBase(self.doc).query(
            "c:task:release", "r:status:blocked", "c:value:true", "ctx:project-alpha", valid_at
        )

    def test_evidence_keeps_both_sources_and_premise_ids(self) -> None:
        proof, = self.query()["evidence"]
        self.assertEqual(proof["assertion_id"], f"derived:{self.need['id']}+{self.lack['id']}")
        self.assertEqual(proof["sources"], self.need["sources"] + self.lack["sources"])
        self.assertEqual(proof["premises"], [self.need["id"], self.lack["id"]])

    def test_each_positive_premise_is_required(self) -> None:
        for fact in [self.need, self.lack]:
            with self.subTest(fact=fact["id"]):
                with patch.dict(fact, polarity="negative"):
                    self.assertEqual(self.query()["evidence"], [])

    def test_report_and_need_alone_do_not_prove_resource_unavailable(self) -> None:
        self.doc["assertions"] = [self.need, self.report]
        self.assertEqual(self.query()["status"], "未知")

    def test_resource_binding_and_exact_value(self) -> None:
        for role, replacement in [("subject", "c:task:release"), ("object", "c:resource:signing-key")]:
            with self.subTest(role=role):
                other = deepcopy(self.lack)
                other["roles"][role] = replacement
                self.doc["assertions"] = [self.need, other]
                self.assertEqual(self.query()["evidence"], [])

    def test_partitions_isolate_the_premises(self) -> None:
        for field, value in [("context", "ctx:other"), ("valid_at", "2026-11-20")]:
            with self.subTest(field=field):
                self.doc["assertions"] = [self.need, {**self.lack, field: value}]
                self.assertEqual(self.query()["status"], "未知")

    def test_undated_partition(self) -> None:
        del self.need["valid_at"]
        self.assertEqual(self.query(None)["status"], "未知")
        del self.lack["valid_at"]
        self.assertEqual(self.query(None)["status"], "支持")
        self.assertEqual(self.query()["status"], "未知")
