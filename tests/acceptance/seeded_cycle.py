"""IR 0.2 有种子循环。每个排列在有超时限制的独立进程中运行。"""

import itertools
import json
from pathlib import Path
import subprocess
import sys
import unittest


def evaluate(reverse_facts, reverse_rules):
    from ncsc import KnowledgeBase

    a, b = "r:a", "r:b"
    seeds = [
        {"id": "a:" + n, "roles": {"subject": "c:x", "relation": a, "object": "c:y"},
         "polarity": "positive", "context": "ctx:test", "valid_at": "2026-11-20",
         "sources": [{"id": "src:" + n, "description": "独立合成来源" + n}]}
        for n in ("1", "2")
    ]
    def ground_rule(name, before, after):
        def term(relation):
            return {"subject": "c:x", "relation": relation, "object": "c:y", "polarity": "positive"}
        return {"format": "ncsc-rules/0.2", "id": name, "status": "active", "description": name,
                "premises": [term(before)], "conclusion": term(after)}

    rules = [ground_rule("forward", a, b), ground_rule("back", b, a)]
    doc = {"version": "0.2", "concepts": [
        {"id": cid, "kind": kind, "aliases": [alias]}
        for cid, kind, alias in [("c:x", "entity", "甲"), ("c:y", "value", "乙"),
                                 (a, "relation", "状态甲"), (b, "relation", "状态乙")]
    ], "assertions": seeds[::-1] if reverse_facts else seeds}
    results = []
    for seeded, derived, rule_id in ((a, b, "forward"), (b, a, "back")):
        for seed in seeds:
            seed["roles"]["relation"] = seeded
        kb = KnowledgeBase(doc, rules[::-1] if reverse_rules else rules)
        for relation in (seeded, derived):
            answer = kb.query("c:x", relation, "c:y", "ctx:test", "2026-11-20")
            evidence = answer["evidence"]
            if answer["status"] != "支持" or len(evidence) != 2:
                raise AssertionError("每个种子应留下一个有限证明")
            if relation == derived and any(node["derived_by"] != rule_id for node in evidence):
                raise AssertionError("应使用对应方向的规则")
            sources = {s["id"] for node in evidence for s in node["sources"]}
            if sources != {"src:1", "src:2"}:
                raise AssertionError("来源与两个原始种子不符")
            results.append(answer)
    return json.dumps(results, ensure_ascii=False, sort_keys=True)


class SeededCycle(unittest.TestCase):
    def test_seeded_cycle_terminates_and_is_order_independent(self):
        outputs = set()
        for facts, rules in itertools.product((0, 1), repeat=2):
            with self.subTest(reverse_facts=facts, reverse_rules=rules):
                run = subprocess.run([sys.executable, "-X", "utf8", __file__, str(facts), str(rules)],
                                     capture_output=True, encoding="utf-8", timeout=5)
                self.assertEqual(run.returncode, 0, run.stderr)
                outputs.add(run.stdout)
        if outputs:
            self.assertEqual(len(outputs), 1, "输入顺序改变了解释")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        print(evaluate(int(sys.argv[1]), int(sys.argv[2])))
    else:
        unittest.main()
