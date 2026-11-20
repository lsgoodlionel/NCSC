import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/synthetic-v0"
RULES = ROOT / "tests/contract/fixtures/rules-0.2/valid"
R1 = RULES / "r1-resource-unavailable.json"


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


class PreviewCLI(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def run_query(self, doc, query, rules, *, budget=None, error_code=0):
        path = self.tmp / "ir.json"
        path.write_text(json.dumps(doc), encoding="utf8")
        args = [sys.executable, "-X", "utf8", "-m", "ncsc.cli", "query-preview", str(path)]
        for key, val in query.items():
            if val is not None:
                args.extend(["--" + key.replace("_", "-"), val])
        for rule in rules:
            args.extend(["--rule", str(rule)])
        if budget is not None:
            args.extend(["--trace-budget", str(budget)])
        result = subprocess.run(args, cwd=ROOT, capture_output=True, encoding="utf8", timeout=8)
        self.assertEqual(result.returncode, error_code, result.stderr)
        if error_code:
            self.assertEqual(result.stdout, "")
            return json.loads(result.stderr)
        return json.loads(result.stdout)

    def test_trace_budget_exact_boundary_and_broad_join(self):
        doc = self.extended_example([])
        q = read(ROOT / "tests/contract/cases/d1-control-no-conflict.json")["queries"][0]["query"]
        expected = self.run_query(doc, q, [R1])
        self.assertEqual(self.run_query(doc, q, [R1], budget=8), expected)
        self.assertEqual(self.run_query(doc, q, [R1], budget=7, error_code=3),
                         {"error": "trace_limit_exceeded", "resource": "trace_budget", "limit": 7})
        for invalid in (0, 10001):
            self.assertFalse(self.run_query(doc, q, [R1], budget=invalid, error_code=2)["valid"])
        need, unavailable = doc["assertions"][:2]
        doc["assertions"] = [dict(fact, id=f"a:{i}-{j}") for i, fact in enumerate((need, unavailable))
                             for j in range(101)]
        error = self.run_query(doc, q, [R1], error_code=3)
        self.assertEqual(error["resource"], "trace_budget")
        doc["assertions"].reverse()
        self.assertEqual(self.run_query(doc, q, [R1], error_code=3), error)

    def test_trace_depth_rejected_before_recursion_limit(self):
        tasks = [f"c:step:{i}" for i in range(50)]
        dep = "r:task:depends-on"
        doc = self.extended_example([dep] + tasks)
        for i, (child, parent) in enumerate(zip(tasks, ["c:task:release"] + tasks)):
            doc["assertions"].append(self.fact(f"a:link:{i}", child, dep, parent))
        chain = self.active_copy("chain-blocked-delays-release.json")
        q = dict(subject=tasks[-1], relation="r:status:blocked", object="c:value:true",
                 context="ctx:project-alpha", valid_at="2026-11-19")
        self.assertEqual(self.run_query(doc, q, [R1, chain], error_code=3),
                         {"error": "trace_limit_exceeded", "resource": "trace_depth", "limit": 48})

    def test_seed_set_without_version_downgrade(self):
        concepts = read(DATA / "registry.json")["concepts"]
        for item in read(DATA / "items.json")["items"]:
            doc = dict(version="0.2", concepts=concepts, assertions=item["assertions"])
            for case in item["queries"]:
                with self.subTest(item=item["id"], query=case["id"]):
                    out = self.run_query(doc, case["query"], [R1])
                    expected = case["expect"]
                    self.assertEqual(out["status"], expected["status"])
                    graph = out["experimental_graph"]
                    expected_ids = {aid for e in expected["evidence"]
                                    for aid in (e["premises"] if "derived_by" in e else [e["assertion_id"]])}
                    self.assertEqual(set(graph["originals"]), expected_ids)
                    self.assertEqual([e["rule"] for e in graph["edges"]],
                                     [e["derived_by"] for e in expected["evidence"] if "derived_by" in e])
                    self.assertEqual([e["premise_originals"] for e in out["suppressed_preview"]],
                                     [[[aid] for aid in group] for group in expected["suppressed"]])

    def active_copy(self, name):
        rule = read(RULES / name)
        rule["status"] = "active"
        path = self.tmp / name
        path.write_text(json.dumps(rule), encoding="utf8")
        return path

    def extended_example(self, extras):
        doc = read(ROOT / "tests/contract/fixtures/0.2/valid/example-migrated.json")
        for cid in extras:
            doc["concepts"].append({"id": cid, "kind": "relation" if cid.startswith("r:") else "entity",
                                    "aliases": ["测试项"]})
        return doc

    def fact(self, aid, s, r, o, polarity="positive"):
        return {"id": aid, "roles": {"subject": s, "relation": r, "object": o},
                "polarity": polarity, "sources": [{"id": "src:test", "description": "测试"}],
                "context": "ctx:project-alpha", "valid_at": "2026-11-19"}

    def test_two_hop_and_seeded_cycle_with_actual_cli(self):
        dep, task, nxt = "r:task:depends-on", "c:task:release", "c:next"
        doc = self.extended_example([dep, nxt])
        doc["assertions"].append(self.fact("a:forward", nxt, dep, task))
        chain = self.active_copy("chain-blocked-delays-release.json")
        q = dict(subject=nxt, relation="r:status:blocked", object="c:value:true",
                 context="ctx:project-alpha", valid_at="2026-11-19")
        out = self.run_query(doc, q, [R1, chain])
        self.assertEqual(out["status"], "支持")
        graph = out["experimental_graph"]
        self.assertEqual(len(graph["edges"]), 2)
        self.assertEqual(set(graph["originals"]), {"a:forward", "a:release-requires-key", "a:key-unavailable"})
        doc["assertions"].append(self.fact("a:back", task, dep, nxt))
        first = self.run_query(doc, q, [R1, chain])
        self.assertEqual(first["evidence"], out["evidence"])
        proof, = first["evidence"]
        self.assertEqual(proof["premises"], [e["assertion_id"] for e in proof["trace"]])
        self.assertEqual(proof["trace"][1]["premises"], ["a:release-requires-key", "a:key-unavailable"])
        self.assertEqual(len(first["experimental_graph"]["edges"]), 3)
        self.assertEqual(set(first["experimental_graph"]["originals"]), set(graph["originals"]) | {"a:back"})
        doc["assertions"].reverse()
        self.assertEqual(self.run_query(doc, q, [chain, R1]), first)
        doc["assertions"] = [a for a in doc["assertions"] if a["id"] in ("a:forward", "a:back")]
        self.assertEqual(self.run_query(doc, q, [chain])["status"], "未知")

    def test_reference_proof_and_independent_premise_ids(self):
        doc = self.extended_example([])
        case = read(ROOT / "tests/contract/cases/d1-control-no-conflict.json")["queries"][0]
        q = case["query"]
        expected = case["expect"]["p3-option-a"]["result"]["evidence"]
        self.assertEqual(self.run_query(doc, q, [R1])["evidence"], expected)
        first = doc["assertions"][0]
        doc["assertions"].append(dict(first, id="a:second-need"))
        proofs = self.run_query(doc, q, [R1])["evidence"]
        self.assertEqual(len({e["assertion_id"] for e in proofs}), 2)
        self.assertEqual({e["premises"][0] for e in proofs}, {first["id"], "a:second-need"})
        doc["assertions"].reverse()
        self.assertEqual(self.run_query(doc, q, [R1])["evidence"], proofs)

    def test_gate_polarity_and_partitions(self):
        task, need, gate, passed, unmet = ("c:task:release", "r:task:requires-gate", "c:g",
                                          "r:gate:passed", "r:status:start-condition-unmet")
        doc = self.extended_example([need, gate, passed, unmet])
        rule = self.active_copy("r2-gate-negative-premise.json")
        q = dict(subject=task, relation=unmet, object="c:value:true",
                 context="ctx:project-alpha", valid_at="2026-11-19")
        needs = self.fact("a:need", task, need, gate)
        negative = self.fact("a:neg", gate, passed, "c:value:true", "negative")
        positive = self.fact("a:pos", gate, passed, "c:value:true")
        for extra, status, contested in [
            ([], "未知", False), ([positive], "未知", False), ([negative], "支持", False),
            ([positive, negative], "未知", True),
            ([dict(negative, valid_at="2026-11-20")], "未知", False),
            ([dict(negative, context="ctx:other")], "未知", False)
        ]:
            with self.subTest(extra=extra):
                doc["assertions"] = [needs] + extra
                out = self.run_query(doc, q, [rule])
                self.assertEqual(out["status"], status)
                self.assertEqual(bool(out["suppressed_preview"]), contested)
