"""IR 0.2 正式接口的两跳、分区隔离和前提极性验收。"""
import json
import random
from pathlib import Path
import unittest

from ncsc import KnowledgeBase


ROOT = Path(__file__).resolve().parents[2]
DAY = "2026-11-19"
CTX = "ctx:project-alpha"
TASK = "c:task:release"
NEXT = "c:next"
TRUE = "c:value:true"
BLOCK = "r:status:blocked"
GATE_RESULT = "r:status:start-condition-unmet"


def fact(aid, subject, relation, obj, polarity="positive"):
    return {"id": aid, "roles": {"subject": subject, "relation": relation, "object": obj},
            "context": CTX, "valid_at": DAY, "polarity": polarity,
            "sources": [{"id": "src:" + aid[2:], "description": "独立验收样例"}]}


def leaves(node):
    if "derived_by" not in node:
        return {node["assertion_id"]}
    return set().union(*(leaves(child) for child in node["trace"]))


class M2Probes(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads((ROOT / "tests/contract/fixtures/0.2/valid/example-migrated.json").read_text(encoding="utf8"))
        for cid in (NEXT, "c:gate", "r:task:depends-on", "r:task:requires-gate",
                    "r:gate:passed", GATE_RESULT):
            self.doc["concepts"].append({"id": cid, "kind": "relation" if cid.startswith("r:") else "entity",
                                         "aliases": ["测试项"]})

        self.rules = []
        path = ROOT / "tests/contract/fixtures/rules-0.2/valid"
        for filename in ("r1-resource-unavailable", "chain-blocked-delays-release", "r2-gate-negative-premise"):
            rule = json.loads((path / (filename + ".json")).read_text(encoding="utf8"))
            rule["status"] = "active"
            self.rules.append(rule)

    def run_query(self, subject, relation):
        return KnowledgeBase(self.doc, self.rules).query(subject, relation, TRUE, CTX, DAY)

    def test_partition_isolation_with_positive_control(self):
        self.assertEqual(self.run_query(TASK, BLOCK)["status"], "支持")
        premise = self.doc["assertions"][1]
        for key, other in (("context", "ctx:other"), ("valid_at", "2026-11-20")):
            with self.subTest(key=key):
                original = premise[key]
                premise[key] = other
                self.assertEqual(self.run_query(TASK, BLOCK)["status"], "未知")
                premise[key] = original

    def test_p3_conflict_suppresses_positive_premise(self):
        premise = self.doc["assertions"][1]
        self.doc["assertions"].append({**premise, "id": "a:disputed", "polarity": "negative"})
        answer = self.run_query(TASK, BLOCK)
        self.assertEqual(answer["status"], "未知")
        self.assertEqual(answer["reason"], "premise_conflict")
        self.assertIn("a:disputed", answer["suppressed"][0]["contested_premises"][0]["opposing"])

    def test_two_hop_trace_and_order(self):
        self.doc["assertions"].append(fact("a:depends", NEXT, "r:task:depends-on", TASK))
        expected = self.run_query(NEXT, BLOCK)
        self.assertEqual(expected["status"], "支持")
        evidence, = expected["evidence"]
        self.assertEqual(evidence["derived_by"], "blocked_dependency_blocks_task")
        self.assertEqual(leaves(evidence), {"a:depends", "a:release-requires-key", "a:key-unavailable"})
        self.assertIn("resource_unavailable_blocks_task", [e.get("derived_by") for e in evidence["trace"]])
        rng = random.Random(20261120)
        for trial in range(50):
            with self.subTest(trial=trial):
                rng.shuffle(self.doc["assertions"])
                rng.shuffle(self.rules)
                self.assertEqual(self.run_query(NEXT, BLOCK), expected)

    def test_negative_premise(self):
        self.doc["assertions"] = [fact("a:needs", TASK, "r:task:requires-gate", "c:gate")]
        for polarities, expected in [((), "未知"), (("negative",), "支持"),
                                     (("positive",), "未知"), (("negative", "positive"), "未知")]:
            with self.subTest(polarities=polarities):
                self.doc["assertions"][1:] = [
                    fact("a:" + p, "c:gate", "r:gate:passed", TRUE, p) for p in polarities
                ]
                answer = self.run_query(TASK, GATE_RESULT)
                self.assertEqual(answer["status"], expected)
                if len(polarities) == 2:
                    self.assertTrue(answer.get("suppressed"))
                elif expected == "支持":
                    self.assertEqual(leaves(answer["evidence"][0]), {"a:needs", "a:negative"})


if __name__ == "__main__":
    unittest.main()
