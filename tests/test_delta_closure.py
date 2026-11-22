"""增量闭包与全匹配参考求值器的差分回归。"""
from itertools import product
import unittest

from ncsc.query_preview import Edge, _closure, _JoinBudget


def pattern(relation, polarity="positive"):
    return dict(subject="?x", relation=relation, object="?y", polarity=polarity)


def rule(name, premises, conclusion):
    return dict(id=name, premises=premises, conclusion=pattern(conclusion))


def reference(originals, rules):
    facts = set(originals)
    while True:
        matches = set()
        for item in rules:
            for premises in product(facts, repeat=len(item["premises"])):
                # 此夹具所有规则都共享 (?x, ?y)，直接用角色相等性定义参考连接。
                first = premises[0]
                if all((s, r, o, p) == (first[0], pat["relation"], first[2], pat["polarity"])
                       for (s, r, o, p), pat in zip(premises, item["premises"])):
                    matches.add(Edge(item["id"], premises,
                                     (first[0], item["conclusion"]["relation"], first[2], "positive")))
        accepted = {e for e in matches if all(
            (s, r, o, "negative" if p == "positive" else "positive") not in facts
            for s, r, o, p in e.premises)}
        new = {e.result for e in accepted} - facts
        if not new:
            return facts, matches, accepted
        facts.update(new)


class DeltaClosure(unittest.TestCase):
    def test_different_premise_rounds_cycles_and_suppressed_edges(self):
        rules = [
            rule("ab", [pattern("a")], "b"), rule("ac", [pattern("a")], "c"),
            rule("loop", [pattern("b")], "a"),
            rule("merge", [pattern("b"), pattern("c"), pattern("a")], "d"),
            rule("late_left", [pattern("d"), pattern("b")], "e"),
            rule("late_right", [pattern("b"), pattern("d")], "e"),
            rule("negative", [pattern("e"), pattern("g", "negative")], "f"),
        ]
        facts = {(s, "a", "y", "positive") for s in ("x", "z")}
        facts.update({("x", "g", "y", "negative"), ("z", "g", "y", "negative"),
                      ("z", "g", "y", "positive")})
        originals = dict.fromkeys(facts, [])
        expected = reference(originals, rules)
        self.assertIn(("x", "f", "y", "positive"), expected[0])
        self.assertNotIn(("z", "f", "y", "positive"), expected[0])
        self.assertTrue(expected[1] - expected[2])
        for order in (rules, list(reversed(rules))):
            self.assertEqual(_closure(originals, order, _JoinBudget()), expected)

    def test_each_unary_match_is_retained_once_across_rounds(self):
        rules = [rule(f"step{i}", [pattern(str(i))], str(i + 1)) for i in range(12)]
        originals = {("x", "0", "y", "positive"): []}
        budget = _JoinBudget()
        facts, matches, accepted = _closure(originals, rules, budget)
        self.assertEqual(len(facts), 13)
        self.assertEqual(len(matches), 12)
        self.assertEqual(matches, accepted)
        self.assertEqual(budget.rows, 12)
