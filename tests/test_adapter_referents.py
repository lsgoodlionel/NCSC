"""#8 开发反例：保持引文与分区不变，单独改变已完成状态的指代。"""
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from adapters.base import propose_ir
from ncsc import KnowledgeBase


REGISTRY = Path(__file__).resolve().parents[1] / "datasets/synthetic-v0/registry.json"
PREFIX = "11月19日，Alpha 项目看板同时列出发布任务和数据迁移任务；"
RELEASE = "c:task:release"
MIGRATION = "c:task:migration"
SOURCE = "src:pm-board"
CONTEXT = "ctx:project-alpha"
DAY = "2026-11-19"


class AdapterReferentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        assert SOURCE in {s["id"] for s in cls.registry["sources"]}
        assert CONTEXT in {c["id"] for c in cls.registry["contexts"]}

    def candidate_answers(self, text, selected):
        assertions = []
        if selected is not None:
            assertions.append({
                "id": "a:board-completion", "context": CONTEXT, "valid_at": DAY,
                "roles": {"subject": selected, "relation": "r:status:completed", "object": "c:value:true"},
                "polarity": "positive", "sources": [{"id": SOURCE, "description": text}],
            })
        stub = Mock(return_value={"version": "0.2", "concepts": self.registry["concepts"],
                                  "assertions": assertions})
        checked = propose_ir(text, "0.2", sources={SOURCE: text}, provider=stub)
        stub.assert_called_once_with(text, "0.2")
        self.assertEqual(checked["status"], "candidate")
        kb = KnowledgeBase(checked["candidate"])
        statuses = []
        for task in (RELEASE, MIGRATION):
            answer = kb.query(task, "r:status:completed", "c:value:true", CONTEXT, DAY)
            if answer["status"] == "支持":
                evidence, = answer["evidence"]
                self.assertEqual(evidence["sources"], [{"id": SOURCE, "description": text}])
            else:
                self.assertEqual(answer["evidence"], [])
            statuses.append(answer["status"])
        return tuple(statuses)

    def test_release_named(self):
        text = PREFIX + "看板明确标记发布任务已完成。"
        self.assertEqual(self.candidate_answers(text, RELEASE), ("支持", "未知"))
        self.assertEqual(self.candidate_answers(text, MIGRATION), ("未知", "支持"))

    def test_migration_named(self):
        text = PREFIX + "看板明确标记数据迁移任务已完成。"
        self.assertEqual(self.candidate_answers(text, MIGRATION), ("未知", "支持"))
        self.assertEqual(self.candidate_answers(text, RELEASE), ("支持", "未知"))

    def test_ambiguous_referent(self):
        text = PREFIX + "看板标记其中一项已完成，但未指明是哪一项。"
        # ambiguous：原文未指明任务，两个具体任务的完成状态均保留为未知。
        self.assertEqual(self.candidate_answers(text, None), ("未知", "未知"))
        self.assertEqual(self.candidate_answers(text, RELEASE), ("支持", "未知"))
        self.assertEqual(self.candidate_answers(text, MIGRATION), ("未知", "支持"))
