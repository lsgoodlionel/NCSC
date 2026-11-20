"""IR 0.1 的固定正向规则；输入是通过校验的原始断言。"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from typing import Any


Assertion = dict[str, Any]
Rule = Callable[[Sequence[Assertion]], Iterator[Assertion]]


def _resource_unavailable_blocks_task(assertions: Sequence[Assertion]) -> Iterator[Assertion]:
    """同一上下文和日期内，任务需要的资源明确不可用时推导任务阻塞。"""
    unavailable: dict[tuple[str, str, str | None], list[Assertion]] = {}
    for fact in assertions:
        roles = fact["roles"]
        if (
            fact["polarity"] == "positive"
            and roles["relation"] == "r:resource:unavailable"
            and roles["object"] == "c:value:true"
        ):
            key = (roles["subject"], fact["context"], fact.get("valid_at"))
            unavailable.setdefault(key, []).append(fact)

    for need in assertions:
        roles = need["roles"]
        if need["polarity"] != "positive" or roles["relation"] != "r:task:requires":
            continue
        key = (roles["object"], need["context"], need.get("valid_at"))
        for lack in unavailable.get(key, []):
            conclusion: Assertion = {
                "id": f"derived:{need['id']}+{lack['id']}",
                "roles": {"subject": roles["subject"], "relation": "r:status:blocked", "object": "c:value:true"},
                "polarity": "positive",
                "context": need["context"],
                "sources": need["sources"] + lack["sources"],
                "_premises": (need["id"], lack["id"]),
            }
            if "valid_at" in need:
                conclusion["valid_at"] = need["valid_at"]
            yield conclusion


# 仅列在此处的实现会执行；规则输入不包含本次推导的结论。
INITIAL_RULES: tuple[tuple[str, Rule], ...] = (
    ("resource_unavailable_blocks_task", _resource_unavailable_blocks_task),
)


def derive_initial_assertions(assertions: Sequence[Assertion]) -> Iterator[Assertion]:
    for rule_id, evaluate in INITIAL_RULES:
        for conclusion in evaluate(assertions):
            conclusion["_derived_by"] = rule_id
            yield conclusion


def default_rules_02(declared: set[str]) -> list[dict[str, Any]]:
    """使用文档词表中的 R1。只含其他概念的词表无默认规则。"""
    constants = {"r:task:requires", "r:resource:unavailable", "r:status:blocked", "c:value:true"}
    if not constants <= declared:
        return []
    return [{
        "format": "ncsc-rules/0.2", "id": "resource_unavailable_blocks_task", "status": "active",
        "description": "同一分区内，任务需要的资源被确认不可用时，推出任务阻塞。",
        "premises": [
            {"subject": "?task", "relation": "r:task:requires", "object": "?resource", "polarity": "positive"},
            {"subject": "?resource", "relation": "r:resource:unavailable", "object": "c:value:true", "polarity": "positive"},
        ],
        "conclusion": {"subject": "?task", "relation": "r:status:blocked", "object": "c:value:true", "polarity": "positive"},
    }]
