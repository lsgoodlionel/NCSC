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
