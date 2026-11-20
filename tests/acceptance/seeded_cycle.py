"""#5 待实现验收：python tests/acceptance/seeded_cycle.py（从仓库根目录运行）。

ground_rule 是临时测试适配器；P-4 实现后只需把规则注入换成加载器。
子进程超时或未运行回边均算失败。本用例独立运行，等待引擎就绪后纳入 CI。
"""

import itertools
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


def evaluate(reverse_facts, reverse_rules):
    from ncsc import KnowledgeBase

    a, b = "r:a", "r:b"
    seeds = [
        {"id": "a:" + n, "roles": {"subject": "c:x", "relation": a, "object": "c:y"},
         "polarity": "positive", "context": "ctx:test", "valid_at": "2026-11-20",
         "sources": [{"id": "src:" + n, "description": "独立合成来源" + n}]}
        for n in ("1", "2")
    ]
    fired = set()

    def ground_rule(name, before, after):
        def apply(facts):
            for f in facts:
                if f["roles"]["relation"] == before and f["polarity"] == "positive":
                    fired.add(name)
                    yield {**f, "id": name + ":" + f["id"],
                           "roles": {**f["roles"], "relation": after},
                           "_premises": (f["id"],)}
        return name, apply

    rules = [ground_rule("forward", a, b), ground_rule("back", b, a)]
    doc = {"version": "0.1", "concepts": [
        {"id": cid, "kind": kind, "aliases": [alias]}
        for cid, kind, alias in [("c:x", "实体", "甲"), ("c:y", "值", "乙"),
                                 (a, "关系", "状态甲"), (b, "关系", "状态乙")]
    ], "assertions": seeds[::-1] if reverse_facts else seeds}
    with patch("ncsc.rules.INITIAL_RULES", rules[::-1] if reverse_rules else rules):
        kb = KnowledgeBase(doc)
        if fired != {"forward", "back"}:
            raise AssertionError(f"未实际遍历完整循环，已触发 {sorted(fired)}")
        facts = {(f["context"], f.get("valid_at"), *[f["roles"][k] for k in
                  ("subject", "relation", "object")], f["polarity"]) for f in kb.assertions}
        expected = {("ctx:test", "2026-11-20", "c:x", r, "c:y", "positive") for r in (a, b)}
        if facts != expected:
            raise AssertionError("事实集合偏离预期")
        def snapshot():
            result = []
            for rel in (a, b):
                answer = kb.query("c:x", rel, "c:y", "ctx:test", "2026-11-20")
                sources = {s["id"] for e in answer["evidence"] for s in e["sources"]}
                if answer["status"] != "支持" or not sources:
                    raise AssertionError("缺少支持证据")
                if rel == a and sources != {"src:1", "src:2"}:
                    raise AssertionError("种子来源丢失")
                if not sources <= {"src:1", "src:2"}:
                    raise AssertionError("出现未知来源")
                result.append(answer)
            return json.dumps(result, ensure_ascii=False, sort_keys=True)
        first = snapshot()
        if first != snapshot():
            raise AssertionError("重复查询改变解释")
        return first


class SeededCycle(unittest.TestCase):
    def test_seeded_cycle_terminates_and_is_order_independent(self):
        outputs = set()
        for facts, rules in itertools.product((0, 1), repeat=2):
            with self.subTest(reverse_facts=facts, reverse_rules=rules):
                run = subprocess.run([sys.executable, __file__, str(facts), str(rules)],
                                     capture_output=True, text=True, timeout=5)
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
