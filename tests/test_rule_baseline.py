import json
from pathlib import Path
import unittest

from baselines.rule_engine import predictions


DATA = Path(__file__).resolve().parents[1] / "datasets/synthetic-v0/items.json"


class RuleBaselineTests(unittest.TestCase):
    def test_all_seed_answers_and_original_evidence(self):
        data = json.loads(DATA.read_text(encoding="utf-8"))
        expected = {}
        for item in data["items"]:
            polarities = {a["id"]: a["polarity"] for a in item["assertions"]}
            for row in item["queries"]:
                gold = row.pop("expect")
                evidence = [
                    dict(e, polarity=polarities[e["assertion_id"]] if "assertion_id" in e else "positive")
                    for e in gold["evidence"]
                ]
                expected[item["id"], row["id"]] = (gold["status"], evidence)
            item["assertions"].reverse()
        actual = {(r["item_id"], r["query_id"]): (r["status"], r["evidence"]) for r in predictions(data)}
        self.assertEqual(actual, expected)

    def test_alternative_leaves_and_contested_resource(self):
        data = json.loads(DATA.read_text(encoding="utf-8"))
        item = next(i for i in data["items"] if i["id"] == "syn-v0-013")
        data["items"] = [item]
        query = next(q for q in item["queries"] if q["expect"]["suppressed"])
        item["queries"] = [query]
        need, unavailable = query["expect"]["suppressed"][0]
        first, = predictions(data)
        self.assertEqual((first["status"], first["evidence"]), ("未知", []))
        # 反证移到无日期分区，同一资源的两个独立来源产生两条前提路径。
        unavailable_fact = next(a for a in item["assertions"] if a["id"] == unavailable)
        opposing = next(a for a in item["assertions"] if a["polarity"] == "negative")
        opposing.pop("valid_at")
        item["assertions"].append(dict(unavailable_fact, id="a:second"))
        result, = predictions(data)
        self.assertEqual(result["status"], "支持")
        self.assertEqual([e["premises"] for e in result["evidence"]],
                         sorted([[need, unavailable], [need, "a:second"]]))
        item["assertions"].reverse()
        self.assertEqual(list(predictions(data)), [result])

    def test_conflicted_resource_does_not_suppress_an_independent_resource(self):
        data = json.loads(DATA.read_text(encoding="utf-8"))
        item = next(i for i in data["items"] if i["id"] == "syn-v0-013")
        query = next(q for q in item["queries"] if q["expect"]["suppressed"])
        data["items"] = [item]
        item["queries"] = [query]
        by_id = {a["id"]: a for a in item["assertions"]}
        need, unavailable = [by_id[aid] for aid in query["expect"]["suppressed"][0]]
        spare = "c:resource:backup"
        item["assertions"].extend([
            dict(need, id="a:need-spare", roles=dict(need["roles"], object=spare)),
            dict(unavailable, id="a:spare-unavailable", roles=dict(unavailable["roles"], subject=spare)),
        ])
        result, = predictions(data)
        self.assertEqual(result["status"], "支持")
        self.assertEqual([e["premises"] for e in result["evidence"]], [["a:need-spare", "a:spare-unavailable"]])

    def test_interval_rejected(self):
        with self.assertRaisesRegex(ValueError, "0.2"):
            list(predictions({"ir_version": "0.3", "items": []}))
        data = json.loads(DATA.read_text(encoding="utf-8"))
        data["items"][0]["assertions"][0]["valid_during"] = {"from": "2026-11-19"}
        with self.assertRaisesRegex(ValueError, "valid_during"):
            list(predictions(data))


class DeclarativeRulesTests(unittest.TestCase):
    @staticmethod
    def rule(rid, src, dst, polarity="positive"):
        def atom(rel, sign):
            return {"subject": "?x", "relation": rel, "object": "c:value:true", "polarity": sign}
        return {"id": rid, "description": rid, "status": "active", "format": "ncsc-rules/0.2",
                "premises": [atom(src, polarity)], "conclusion": atom(dst, "positive")}

    def dataset(self, relation, assertions):
        query = {"subject": "c:t", "relation": relation, "object": "c:value:true",
                 "context": "ctx:alpha", "valid_at": None}
        facts = [
            {"id": aid, "roles": {**{k: query[k] for k in ("subject", "object")}, "relation": rel},
             "polarity": polarity, "context": context}
            for aid, rel, polarity, context in assertions
        ]
        return {"ir_version": "0.2", "items": [{"id": "item", "assertions": facts,
                                                 "queries": [{"id": "q", "query": query}]}]}

    def test_chain_with_seeded_cycle_scores_original_leaves(self):
        from baselines.evaluate import score
        rules = [self.rule("ab", "r:a", "r:b"), self.rule("ba", "r:b", "r:a"), self.rule("bc", "r:b", "r:c")]
        data = self.dataset("r:c", [("a:seed1", "r:a", "positive", "ctx:alpha"),
                                    ("a:seed2", "r:a", "positive", "ctx:alpha")])
        expected = [{"derived_by": "bc", "premises": [{"derived_by": "ab", "premises": [aid]}]}
                    for aid in ("a:seed1", "a:seed2")]
        data["items"][0]["queries"][0]["expect"] = {"status": "支持", "evidence": expected}
        result = list(predictions(data, rules))
        self.assertEqual(len(result[0]["evidence"]), 2)
        metrics = score(data, result)
        self.assertEqual(metrics["rule_paths"]["matched"], 2)
        self.assertEqual(metrics["leaves"]["matched"], 2)
        self.assertEqual(metrics["provenance_complete"]["matched"], 1)
        data["items"][0]["assertions"].reverse()
        self.assertEqual(list(predictions(data, rules[::-1])), result)
        data["items"][0]["assertions"] = []
        row, = predictions(data, rules)
        self.assertEqual((row["status"], row["evidence"]), ("未知", []))

    def test_explicit_negative_is_partitioned_and_suppressed_on_conflict(self):
        rule = self.rule("failed", "r:gate", "r:blocked", "negative")
        data = self.dataset("r:blocked", [("a:other", "r:gate", "negative", "ctx:other")])
        self.assertEqual(next(predictions(data, [rule]))["status"], "未知")
        fact = data["items"][0]["assertions"][0]
        data["items"][0]["assertions"].append(dict(fact, id="a:here", context="ctx:alpha"))
        self.assertEqual(next(predictions(data, [rule]))["evidence"][0]["premises"], ["a:here"])
        data["items"][0]["assertions"].append(dict(fact, id="a:confirmed", context="ctx:alpha", polarity="positive"))
        self.assertEqual(next(predictions(data, [rule]))["status"], "未知")
        with self.assertRaisesRegex(ValueError, "负向前提"):
            list(predictions(data, [rule, self.rule("enable", "r:check", "r:gate")]))

    def test_unsafe_rules_rejected(self):
        data = self.dataset("r:c", [])
        rule = self.rule("ab", "r:a", "r:b")
        for update in ({"subject": "?unbound"}, {"polarity": "negative"}, {"relation": "r:claim:reported-cause"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                list(predictions(data, [dict(rule, conclusion=dict(rule["conclusion"], **update))]))
