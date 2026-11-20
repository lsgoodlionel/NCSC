"""0.2 局部查询原型。事实按分区闭包；解释为有限图，不展开递归证明 ID。"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from itertools import product
import json
from typing import Any, Dict, FrozenSet, Iterable, Iterator, List, NamedTuple, Set, Tuple

from .core import IRValidationError, _check_id, _validate_day, validate_document
from .rule_loader import load_rules

Fact = Tuple[str, str, str, str]
Binding = Dict[str, str]
DEFAULT_TRACE_BUDGET = 10000
MAX_TRACE_DEPTH = 48
MAX_JOIN_ATTEMPTS = 1_000_000
MAX_JOIN_ROWS = 8192


class QueryLimitError(Exception):
    def __init__(self, resource: str, limit: int):
        self.resource = resource
        self.limit = limit
        super().__init__(f"查询资源超限: {resource}={limit}")


class TraceLimitError(QueryLimitError):
    pass


class _JoinBudget:
    def __init__(self) -> None:
        self.attempts = 0
        self.rows = 0

    def attempt(self) -> None:
        self.attempts += 1
        if self.attempts > MAX_JOIN_ATTEMPTS:
            raise QueryLimitError("join_attempts", MAX_JOIN_ATTEMPTS)

    def retain(self) -> None:
        self.rows += 1
        if self.rows > MAX_JOIN_ROWS:
            raise QueryLimitError("join_rows", MAX_JOIN_ROWS)


class _Budget:
    def __init__(self, limit: int):
        if type(limit) is not int or not 1 <= limit <= DEFAULT_TRACE_BUDGET:
            raise IRValidationError(f"trace_budget 须为 1–{DEFAULT_TRACE_BUDGET} 的整数")
        self.limit = limit
        self.remaining = limit

    def charge(self, units: int = 1) -> None:
        if units > self.remaining:
            raise TraceLimitError("trace_budget", self.limit)
        self.remaining -= units


class Edge(NamedTuple):
    rule: str
    premises: Tuple[Fact, ...]
    result: Fact


def _ground(pattern: Dict[str, str], binding: Binding) -> Fact:
    return (binding.get(pattern["subject"], pattern["subject"]), pattern["relation"],
            binding.get(pattern["object"], pattern["object"]), pattern["polarity"])


def _matches(rule: Dict[str, Any], facts: Set[Fact], budget: _JoinBudget) -> Iterator[Edge]:
    rows: List[Tuple[Binding, Tuple[Fact, ...]]] = [({}, ())]
    for pattern in rule["premises"]:
        joined = []
        for s, r, o, p in facts:
            budget.attempt()
            if (r, p) != (pattern["relation"], pattern["polarity"]):
                continue
            for binding, premises in rows:
                budget.attempt()
                extended = binding.copy()
                for term, val in ((pattern["subject"], s), (pattern["object"], o)):
                    if term.startswith("?"):
                        term = extended.setdefault(term, val)
                    if term != val:
                        break
                else:
                    budget.retain()
                    joined.append((extended, premises + ((s, r, o, p),)))
        rows = joined
        if not rows:
            return
    for binding, premises in rows:
        yield Edge(rule["id"], premises, _ground(rule["conclusion"], binding))


def _opposite(fact: Fact) -> Fact:
    s, r, o, polarity = fact
    return s, r, o, "negative" if polarity == "positive" else "positive"


def _proofs(fact: Fact, ancestors: FrozenSet[Fact], by_result: Dict[Fact, List[Edge]],
            originals: Dict[Fact, List[str]], assertions: Dict[str, Any],
            budget: _Budget) -> Iterator[Tuple[Dict[str, Any], int]]:
    """每条根到叶路径内事实唯一；兄弟前提各自保留独立的祖先集合。"""
    budget.charge()
    if fact in ancestors:
        return
    if len(ancestors) >= MAX_TRACE_DEPTH:
        raise TraceLimitError("trace_depth", MAX_TRACE_DEPTH)
    for aid in sorted(originals.get(fact, [])):
        budget.charge()
        yield {"assertion_id": aid, "polarity": fact[3], "sources": assertions[aid]["sources"]}, 1
    path = ancestors | {fact}
    for edge in sorted(by_result.get(fact, [])):
        options = [_proofs(p, path, by_result, originals, assertions, budget) for p in edge.premises]
        for combination in product(*options):
            # product 复用子证明；按序列化后每次出现的节点计费，避免共享引用掩盖指数增长。
            size = 1 + sum(weight for _, weight in combination)
            budget.charge(size)
            children = [node for node, _ in combination]
            ids = [child["assertion_id"] for child in children]
            payload = json.dumps([edge.rule, ids], separators=(",", ":"), ensure_ascii=False)
            digest = sha256(payload.encode("utf-8")).hexdigest()[:32]
            sources = {}
            for child in children:
                for source in child["sources"]:
                    sources.setdefault(source["id"], source)
            yield {"assertion_id": f"d:{edge.rule}:{digest}", "polarity": fact[3],
                   "derived_by": edge.rule, "premises": ids, "sources": list(sources.values()),
                   "trace": children}, size


def query_preview(document: Any, rules: Iterable[Any], subject: str, relation: str,
                  obj: str, context: str, day: str | None, *,
                  trace_budget: int = DEFAULT_TRACE_BUDGET) -> Dict[str, Any]:
    budget = _Budget(trace_budget)
    doc = validate_document(document)
    if doc["version"] != "0.2":
        raise IRValidationError("query-preview 仅用于 IR 0.2")
    declared = {c["id"] for c in doc["concepts"]}
    for value, prefix in ((subject, "c"), (relation, "r"), (obj, "c")):
        _check_id(value, prefix, "query")
        if value not in declared:
            raise IRValidationError(f"undeclared_concept: {value}")
    _check_id(context, "ctx", "query.context")
    if day is not None:
        _validate_day(day, "query.valid_at")
    active = load_rules(rules, declared)
    originals: Dict[Fact, List[str]] = defaultdict(list)
    for a in doc["assertions"]:
        if (a["context"], a.get("valid_at")) == (context, day):
            roles = a["roles"]
            originals[roles["subject"], roles["relation"], roles["object"], a["polarity"]].append(a["id"])

    facts = set(originals)
    join_budget = _JoinBudget()
    while True:
        matches = {edge for rule in active for edge in _matches(rule, facts, join_budget)}
        accepted = {edge for edge in matches if all(_opposite(p) not in facts for p in edge.premises)}
        new = {edge.result for edge in accepted} - facts
        if not new:
            break
        facts.update(new)

    pos: Fact = (subject, relation, obj, "positive")
    neg = _opposite(pos)
    status = {(True, True): "冲突", (True, False): "支持",
              (False, True): "反对", (False, False): "未知"}[(pos in facts, neg in facts)]
    by_result: Dict[Fact, List[Edge]] = defaultdict(list)
    for edge in accepted:
        by_result[edge.result].append(edge)
    queue = [f for f in (pos, neg) if f in facts]
    visited: Set[Fact] = set()
    reachable: Set[Edge] = set()
    while queue:
        current = queue.pop()
        if current not in visited:
            visited.add(current)
            for edge in by_result[current]:
                reachable.add(edge)
                queue.extend(edge.premises)

    suppressed = []
    for ids in originals.values():
        ids.sort()
    for edge in sorted(matches - accepted):
        if edge.result == pos:
            suppressed.append({**edge._asdict(),
                               "premise_originals": [originals[p] for p in edge.premises],
                               "contested": [_opposite(p) for p in edge.premises if _opposite(p) in facts]})
    assertions = {a["id"]: a for a in doc["assertions"]}
    evidence = sorted((e for root in (pos, neg) if root in facts
                       for e, _ in _proofs(root, frozenset(), by_result, originals, assertions, budget)),
                      key=lambda e: e["assertion_id"])
    return {"status": status, "context": context, "valid_at": day, "evidence": evidence,
            "experimental_graph": {"edges": [e._asdict() for e in sorted(reachable)],
                                   "originals": sorted(aid for f in visited for aid in originals[f])},
            "suppressed_preview": suppressed}
