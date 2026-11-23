import unittest

from baselines import json_exact, kg, rule_engine


def atom(rel, polarity="positive"):
    return {"subject": "c:task", "relation": rel, "object": "c:value:true", "polarity": polarity}


def rule(src, dst):
    return {"format": "ncsc-rules/0.2", "id": dst[2:], "status": "active", "description": "逐步推导",
            "premises": [atom(src)], "conclusion": atom(dst)}


def dataset(rel):
    sources = [{"id": "src:one", "description": "状态记录"},
               {"id": "src:two", "description": "复核记录"}]
    fact = atom("r:a")
    roles = {k: fact[k] for k in json_exact.ROLES}
    claim = {"id": "a:root", "roles": roles, "context": "ctx:one", "polarity": "positive",
             "sources": sources}
    query = {**roles, "relation": rel, "context": "ctx:one", "valid_at": None}
    return {"ir_version": "0.2", "items": [{"id": "item", "assertions": [claim],
                                            "queries": [{"id": "q", "query": query}]}]}


class SourcePredictionTests(unittest.TestCase):
    def test_direct_sources_are_reported_on_request(self):
        data = dataset("r:a")
        fact = data["items"][0]["assertions"][0]
        expected = {"assertion_id": fact["id"], "polarity": "positive"}
        for system in (json_exact, kg, rule_engine):
            with self.subTest(system=system.__name__):
                result, = system.predictions(data)
                self.assertEqual(result["evidence"], [expected])
                sourced, = system.predictions(data, include_sources=True)
                self.assertEqual(sourced["evidence"], [dict(expected, sources=fact["sources"])])

    def test_sqlite_reports_sources_down_to_multihop_leaves(self):
        data = dataset("r:c")
        fact = data["items"][0]["assertions"][0]
        result, = rule_engine.predictions(data, [rule("r:a", "r:b"), rule("r:b", "r:c")], include_sources=True)
        root, = result["evidence"]
        middle, = root["trace"]
        leaf, = middle["trace"]
        self.assertEqual(root["premises"], [middle["assertion_id"]])
        self.assertEqual(middle["premises"], [fact["id"]])
        self.assertEqual(leaf, {"assertion_id": fact["id"], "polarity": "positive", "sources": fact["sources"]})
