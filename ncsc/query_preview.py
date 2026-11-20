"""0.2 局部查询原型。事实按分区闭包；解释为有限图，不展开递归证明 ID。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, Iterator, List, NamedTuple, Set, Tuple

from .core import IRValidationError, _check_id, _validate_day, validate_document
from .rule_loader import load_rules

Fact = Tuple[str, str, str, str]
Binding = Dict[str, str]


class Edge(NamedTuple):
    rule: str
    premises: Tuple[Fact, ...]
    result: Fact


def _ground(pattern: Dict[str, str], binding: Binding) -> Fact:
    return (binding.get(pattern["subject"], pattern["subject"]), pattern["relation"],
            binding.get(pattern["object"], pattern["object"]), pattern["polarity"])


def _matches(rule: Dict[str, Any], facts: Set[Fact]) -> Iterator[Edge]:
    rows: List[Tuple[Binding, Tuple[Fact, ...]]] = [({}, ())]
    for pattern in rule["premises"]:
        joined = []
        for s, r, o, p in facts:
            if (r, p) != (pattern["relation"], pattern["polarity"]):
                continue
            for binding, premises in rows:
                extended = binding.copy()
                for term, val in ((pattern["subject"], s), (pattern["object"], o)):
                    if term.startswith("?"):
                        term = extended.setdefault(term, val)
                    if term != val:
                        break
                else:
                    joined.append((extended, premises + ((s, r, o, p),)))
        rows = joined
    for binding, premises in rows:
        yield Edge(rule["id"], premises, _ground(rule["conclusion"], binding))


def _opposite(fact: Fact) -> Fact:
    s, r, o, polarity = fact
    return s, r, o, "negative" if polarity == "positive" else "positive"


def query_preview(document: Any, rules: Iterable[Any], subject: str, relation: str,
                  obj: str, context: str, day: str | None) -> Dict[str, Any]:
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
    while True:
        matches = {edge for rule in active for edge in _matches(rule, facts)}
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
    for edge in sorted(matches - accepted):
        if edge.result == pos:
            suppressed.append({**edge._asdict(),
                               "premise_originals": [sorted(originals[p]) for p in edge.premises],
                               "contested": [_opposite(p) for p in edge.premises if _opposite(p) in facts]})
    return {"status": status, "context": context, "valid_at": day,
            "experimental_graph": {"edges": [e._asdict() for e in sorted(reachable)],
                                   "originals": sorted(aid for f in visited for aid in originals[f])},
            "suppressed_preview": suppressed}
