"""#5 本地实验：同一分区、单前提、正向 ground 规则；不定义生产 trace 契约。

python tests/acceptance/fixed_point_probe.py -v
"""
from collections import defaultdict, deque
from itertools import product
import unittest


def closure(seeds, rules):
    """传播首次出现的 (事实, 原始断言 ID)，返回事实及其可达来源。"""
    successors = defaultdict(set)
    for premise, conclusion in rules:
        successors[premise].add(conclusion)
    reachable = defaultdict(set)
    queue = deque()

    def offer(fact, original):
        if original not in reachable[fact]:
            reachable[fact].add(original)
            queue.append((fact, original))

    for fact, original in seeds:
        offer(fact, original)
    visits = 0
    while queue:
        fact, original = queue.popleft()
        visits += 1
        for conclusion in successors[fact]:
            offer(conclusion, original)
    return {fact: sorted(ids) for fact, ids in sorted(reachable.items())}, visits


class FixedPointProbe(unittest.TestCase):
    def test_seeded_cycle_both_origins(self):
        seeds = [("A", "a:1"), ("A", "a:2")]
        rules = [("A", "B"), ("B", "A")]
        for s, r in product((1, -1), repeat=2):
            with self.subTest(seed_order=s, rule_order=r):
                self.assertEqual(closure(seeds[::s], rules[::r]),
                                 ({"A": ["a:1", "a:2"], "B": ["a:1", "a:2"]}, 4))

    def test_late_origin_reaches_already_derived_fact(self):
        seeds = [("A", "a:1"), ("X", "a:2")]
        rules = [("A", "B"), ("X", "Y"), ("Y", "A"), ("B", "A")]
        facts, visits = closure(seeds, rules)
        self.assertEqual(facts, {"A": ["a:1", "a:2"], "B": ["a:1", "a:2"],
                                 "X": ["a:2"], "Y": ["a:2"]})
        self.assertEqual(visits, 6)

    def test_unseeded_cycle_has_no_evidence(self):
        self.assertEqual(closure([], [("A", "B"), ("B", "A")]), ({}, 0))


if __name__ == "__main__":
    unittest.main()
