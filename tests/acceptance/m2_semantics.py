"""IR 0.2 正式接口的两跳、分区隔离和前提极性验收。"""
import json
import random
from pathlib import Path
import unittest

from ncsc import IRValidationError, KnowledgeBase


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

    def test_d8_ambiguous_ids_and_shared_source(self):
        need, lack = self.doc["assertions"][:2]
        # P-2 的旧拼接形式无法区分这两组前提。新版本在入口拒绝分隔符。
        pairs = [("a:x", "a:y+a:z"), ("a:x+a:y", "a:z")]
        self.assertEqual("+".join(pairs[0]), "+".join(pairs[1]))
        for first, second in pairs:
            self.doc["assertions"] = [dict(need, id=first), dict(lack, id=second)]
            with self.subTest(pair=(first, second)), self.assertRaisesRegex(IRValidationError, "非法 a:"):
                KnowledgeBase(self.doc)

        # 冒号在新 ID 内合法。即使边界可混淆，四种前提组合仍应各有一个证明。
        shared = {"id": "src:shared", "description": "两条记录共同引用的报告"}
        self.doc["assertions"] = [
            dict(need, id=aid, sources=[shared, *need["sources"]]) for aid in ("a:x", "a:x:a:y")
        ] + [
            dict(lack, id=aid, sources=[shared, *lack["sources"]]) for aid in ("a:y:a:z", "a:z")
        ]
        expected_pairs = {(a["id"], b["id"]) for a in self.doc["assertions"][:2]
                          for b in self.doc["assertions"][2:]}
        proofs = self.run_query(TASK, BLOCK)["evidence"]
        self.assertEqual({tuple(proof["premises"]) for proof in proofs}, expected_pairs)
        self.assertEqual(len(proofs), 4)
        self.assertEqual(len({proof["assertion_id"] for proof in proofs}), 4)
        for proof in proofs:
            self.assertEqual(proof["sources"], [shared, *need["sources"], *lack["sources"]])
            self.assertEqual([leaf["sources"][0] for leaf in proof["trace"]], [shared, shared])

    def test_later_proof_reaches_existing_downstream_fact(self):
        # 同一阻塞事实先有直接记录，再由 R1 推出；依赖方应保留两条解释。
        direct = fact("a:direct", TASK, BLOCK, TRUE)
        link = fact("a:depends", NEXT, "r:task:depends-on", TASK)
        self.doc["assertions"].extend([direct, link])
        for version in ("0.2", "0.3"):
            self.doc["version"] = version
            with self.subTest(version=version):
                result = self.run_query(NEXT, BLOCK)
                self.assertEqual(result["status"], "支持")
                proofs = result["evidence"]
                self.assertEqual(len(proofs), 2)
                self.assertEqual({frozenset(leaves(e)) for e in proofs}, {
                    frozenset(["a:depends", "a:direct"]),
                    frozenset(["a:depends", "a:release-requires-key", "a:key-unavailable"]),
                })
                sources_by_id = {a["id"]: a["sources"] for a in self.doc["assertions"]}
                for proof in proofs:
                    expected = {s["id"]: s for aid in leaves(proof) for s in sources_by_id[aid]}
                    self.assertCountEqual(proof["sources"], list(expected.values()))
                self.doc["assertions"].reverse()
                self.assertEqual(self.run_query(NEXT, BLOCK), result)

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
