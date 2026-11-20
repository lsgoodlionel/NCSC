import json
import unittest
from pathlib import Path

from ncsc import IRValidationError, KnowledgeBase


EXAMPLE = Path(__file__).parents[1] / "examples" / "project_state.json"


class CalendarDayTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.fact = self.doc["assertions"][0]
        self.query = {**self.fact["roles"], "context": self.fact["context"]}
        self.query["object_"] = self.query.pop("object")

    def test_regression_d2_loading_and_query_reject_invalid_days(self):
        kb = KnowledgeBase(self.doc)
        for day in ("2026-1-5", "20260105", "2026-W02-1", "2025-02-29",
                    "2026-01-05T00:00:00Z", " 2026-01-05", 20260105):
            with self.subTest(day=day):
                self.fact["valid_at"] = day
                with self.assertRaisesRegex(IRValidationError, r"assertions\[0\]\.valid_at"):
                    KnowledgeBase(self.doc)
                with self.assertRaisesRegex(IRValidationError, "查询 valid_at"):
                    kb.query(**self.query, valid_at=day)

    def test_leap_day_is_queryable_in_its_partition(self):
        self.fact["valid_at"] = "2024-02-29"
        kb = KnowledgeBase(self.doc)
        self.assertEqual(kb.query(**self.query, valid_at="2024-02-29")["status"], "支持")
        self.assertEqual(kb.query(**self.query, valid_at="2024-03-01")["status"], "未知")
