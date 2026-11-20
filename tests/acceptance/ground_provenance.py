"""P-4 多前提局部实验：已绑定、同分区、全正向。独立于生产查询入口。"""
from collections import defaultdict, deque
from typing import NamedTuple
import unittest


class Edge(NamedTuple):
    rule: str
    premises: tuple
    conclusion: str


def derive(seeds, rules):
    """一个事实只入队一次；每个已满足的具体规则实例都有一条解释边。"""
    origins = defaultdict(set)
    for fact, assertion_id in seeds:
        origins[fact].add(assertion_id)
    facts = set(origins)
    queue = deque(facts)
    waiting = defaultdict(set)
    remaining = {}
    edges = set()
    for edge in set(rules):
        if not edge.premises:
            raise ValueError("至少需要一个前提")
        remaining[edge] = len(set(edge.premises))
        for premise in set(edge.premises):
            waiting[premise].add(edge)
    while queue:
        fact = queue.popleft()
        for edge in waiting[fact]:
            remaining[edge] -= 1
            if remaining[edge] == 0:
                edges.add(edge)
                if edge.conclusion not in facts:
                    facts.add(edge.conclusion)
                    queue.append(edge.conclusion)
    return facts, origins, edges


def explanations(target, origins, edges, ancestors=frozenset()):
    """实验选项：路径内重复事实即停止该分支，不剪掉同层的独立替代路径。"""
    if target in ancestors:
        return set()
    from itertools import product

    proofs = {("source", aid) for aid in origins.get(target, ())}
    for edge in edges:
        if edge.conclusion == target:
            children = [explanations(p, origins, edges, ancestors | {target}) for p in edge.premises]
            proofs.update((edge.rule, parents) for parents in product(*children))
    return proofs


class MultiPremiseTests(unittest.TestCase):
    def test_distinct_paths_same_leaves_and_back_edge(self):
        seeds = [("A", "a:1"), ("X", "a:2")]
        rules = [Edge("left", ("A", "X"), "L"), Edge("right", ("A", "X"), "R"),
                 Edge("finish_l", ("L",), "Z"), Edge("finish_r", ("R",), "Z"),
                 Edge("back", ("Z",), "A")]
        leaves = (("source", "a:1"), ("source", "a:2"))
        expected = {("finish_l", (("left", leaves),)), ("finish_r", (("right", leaves),))}
        for s in (seeds, seeds[::-1]):
            for r in (rules, rules[::-1]):
                facts, origins, edges = derive(s, r)
                self.assertEqual(facts, {"A", "X", "L", "R", "Z"})
                self.assertEqual(edges, set(rules))
                self.assertEqual(explanations("Z", origins, edges), expected)

    def test_missing_conjunct_and_unseeded_cycle(self):
        rules = [Edge("join", ("A", "X"), "B"), Edge("back", ("B",), "X")]
        facts, _, edges = derive([("A", "a:1")], rules)
        self.assertEqual(facts, {"A"})
        self.assertFalse(edges)

    def test_alternative_sources_and_ordered_repeated_premise(self):
        facts, origins, edges = derive([("A", "a:1"), ("A", "a:2")],
                                       [Edge("both", ("A", "A"), "B")])
        self.assertEqual(facts, {"A", "B"})
        choices = [("source", "a:1"), ("source", "a:2")]
        self.assertEqual(explanations("B", origins, edges),
                         {("both", (left, right)) for left in choices for right in choices})


if __name__ == "__main__":
    unittest.main()
