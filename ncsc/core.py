"""严格 JSON IR 校验、白名单推理与四值查询。"""

from __future__ import annotations

import datetime as _dt
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

from .rules import default_rules_02, derive_initial_assertions


if TYPE_CHECKING:
    from .query_preview import QueryIndex


class IRValidationError(ValueError):
    """输入不符合共享 IR 契约。"""


ROOT_KEYS = {"version", "concepts", "assertions"}
CONCEPT_KEYS = {"id", "aliases", "kind"}
ASSERTION_KEYS = {"id", "roles", "polarity", "sources", "context", "valid_at"}
ROLE_KEYS = {"subject", "relation", "object"}
SOURCE_KEYS = {"id", "description"}
INTERVAL_KEYS = {"from", "to"}


def _exact_keys(value: Dict[str, Any], allowed: set[str], where: str, required: set[str]) -> None:
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown or missing:
        raise IRValidationError(f"{where}: 未知字段={sorted(unknown)}，缺少字段={sorted(missing)}")


def _nonempty_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IRValidationError(f"{where}: 必须是非空字符串")
    return value


def _validate_day(value: Any, where: str) -> None:
    message = f"{where}: 仅支持 YYYY-MM-DD 单日"
    if not isinstance(value, str):
        raise IRValidationError(message)
    try:
        day = _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise IRValidationError(message) from exc
    if day.isoformat() != value:
        raise IRValidationError(message)


def _validate_interval(value: Any, where: str) -> None:
    if not isinstance(value, dict) or not value:
        raise IRValidationError(f"{where}: 区间必须是含 from 或 to 的对象")
    _exact_keys(value, INTERVAL_KEYS, where, set())
    for endpoint, day in value.items():
        _validate_day(day, f"{where}.{endpoint}")
    if "from" in value and "to" in value and value["from"] > value["to"]:
        raise IRValidationError(f"{where}: from 晚于 to")


_ID_BODY = re.compile(r"[0-9a-z](?:[0-9a-z._:-]{0,126}[0-9a-z])?")
_HAN = re.compile("[㐀-䶿一-鿿豈-﫿]")


def _check_id(value: str, prefix: str, where: str) -> None:
    namespace, _, body = value.partition(":")
    if namespace != prefix or not _ID_BODY.fullmatch(body):
        raise IRValidationError(f"{where}: 非法 {prefix}: 标识符")


def _check_text(value: str, where: str) -> None:
    if value.strip() != value or value.splitlines() != [value]:
        raise IRValidationError(f"{where}: 文本须单行且首尾无空白")


def _validate_v02(doc: Dict[str, Any]) -> None:
    """公共结构和引用已经通过检查；这里只检查 0.2 增量约束。"""
    for i, concept in enumerate(doc["concepts"]):
        where = f"concepts[{i}]"
        kind = concept["kind"]
        if kind not in ("entity", "event", "state", "quality", "value", "relation"):
            raise IRValidationError(f"{where}.kind: 未声明的类别")
        _check_id(concept["id"], "r" if kind == "relation" else "c", f"{where}.id")
        aliases = concept["aliases"]
        for alias in aliases:
            _check_text(alias, f"{where}.aliases")
        if len(set(aliases)) != len(aliases) or not any(_HAN.search(s) for s in aliases):
            raise IRValidationError(f"{where}.aliases: 须概念内唯一且至少有一个含汉字")
    for i, fact in enumerate(doc["assertions"]):
        where = f"assertions[{i}]"
        _check_id(fact["id"], "a", f"{where}.id")
        _check_id(fact["context"], "ctx", f"{where}.context")
        for role, cid in fact["roles"].items():
            _check_id(cid, "r" if role == "relation" else "c", f"{where}.roles.{role}")
        seen = set()
        for j, source in enumerate(fact["sources"]):
            sw = f"{where}.sources[{j}]"
            _check_id(source["id"], "src", f"{sw}.id")
            _check_text(source["description"], f"{sw}.description")
            if source["id"] in seen:
                raise IRValidationError(f"{sw}.id: 同一断言内来源 ID 重复")
            seen.add(source["id"])


def validate_document(doc: Any) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        raise IRValidationError("根节点必须是对象")
    _exact_keys(doc, ROOT_KEYS, "根节点", ROOT_KEYS)
    if doc["version"] not in ("0.1", "0.2", "0.3"):
        raise IRValidationError("仅支持 IR version 0.1 / 0.2 / 0.3")
    if not isinstance(doc["concepts"], list) or not isinstance(doc["assertions"], list):
        raise IRValidationError("concepts 与 assertions 必须是数组")

    concept_ids = set()
    for index, concept in enumerate(doc["concepts"]):
        where = f"concepts[{index}]"
        if not isinstance(concept, dict):
            raise IRValidationError(f"{where}: 必须是对象")
        _exact_keys(concept, CONCEPT_KEYS, where, CONCEPT_KEYS)
        cid = _nonempty_string(concept["id"], f"{where}.id")
        if cid in concept_ids:
            raise IRValidationError(f"{where}: 重复概念 ID {cid}")
        concept_ids.add(cid)
        if not isinstance(concept["aliases"], list) or not concept["aliases"]:
            raise IRValidationError(f"{where}.aliases: 必须是非空数组")
        for alias in concept["aliases"]:
            _nonempty_string(alias, f"{where}.aliases")
        _nonempty_string(concept["kind"], f"{where}.kind")

    allowed = ASSERTION_KEYS | {"valid_during"} if doc["version"] == "0.3" else ASSERTION_KEYS
    assertion_ids = set()
    for index, assertion in enumerate(doc["assertions"]):
        where = f"assertions[{index}]"
        if not isinstance(assertion, dict):
            raise IRValidationError(f"{where}: 必须是对象")
        _exact_keys(assertion, allowed, where, ASSERTION_KEYS - {"valid_at"})
        aid = _nonempty_string(assertion["id"], f"{where}.id")
        if aid in assertion_ids:
            raise IRValidationError(f"{where}: 重复断言 ID {aid}")
        assertion_ids.add(aid)
        roles = assertion["roles"]
        if not isinstance(roles, dict):
            raise IRValidationError(f"{where}.roles: 必须是对象")
        _exact_keys(roles, ROLE_KEYS, f"{where}.roles", ROLE_KEYS)
        for role, cid in roles.items():
            _nonempty_string(cid, f"{where}.roles.{role}")
            if cid not in concept_ids:
                raise IRValidationError(f"{where}.roles.{role}: 未声明概念 {cid}")
        if assertion["polarity"] not in ("positive", "negative"):
            raise IRValidationError(f"{where}.polarity: 仅支持 positive/negative")
        _nonempty_string(assertion["context"], f"{where}.context")
        sources = assertion["sources"]
        if not isinstance(sources, list) or not sources:
            raise IRValidationError(f"{where}.sources: 必须是非空数组")
        for source_index, source in enumerate(sources):
            sw = f"{where}.sources[{source_index}]"
            if not isinstance(source, dict):
                raise IRValidationError(f"{sw}: 必须是对象")
            _exact_keys(source, SOURCE_KEYS, sw, SOURCE_KEYS)
            _nonempty_string(source["id"], f"{sw}.id")
            _nonempty_string(source["description"], f"{sw}.description")
        if "valid_during" in assertion:
            if "valid_at" in assertion:
                raise IRValidationError(f"{where}: valid_at 与 valid_during 不能同时出现")
            _validate_interval(assertion["valid_during"], f"{where}.valid_during")
        elif "valid_at" in assertion:
            _validate_day(assertion["valid_at"], f"{where}.valid_at")
    if doc["version"] in ("0.2", "0.3"):
        _validate_v02(doc)
    return doc


@dataclass(frozen=True)
class Evidence:
    assertion_id: str
    polarity: str
    sources: List[Dict[str, str]]
    derived_by: Optional[str] = None
    premises: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"assertion_id": self.assertion_id, "polarity": self.polarity, "sources": self.sources}
        if self.derived_by:
            result.update({"derived_by": self.derived_by, "premises": list(self.premises)})
        return result


class KnowledgeBase:
    def __init__(self, doc: Dict[str, Any], rules: Optional[Iterable[Any]] = None) -> None:
        self.doc = validate_document(doc)
        if self.doc["version"] in ("0.2", "0.3"):
            self.doc = deepcopy(self.doc)
        self.assertions = list(self.doc["assertions"])
        self._index: Optional[QueryIndex] = None
        self._active: List[Dict[str, Any]] = []
        if self.doc["version"] in ("0.2", "0.3"):
            from .query_preview import QueryIndex
            from .rule_loader import load_rules

            self._index = QueryIndex(self.doc)
            declared = self._index.declared
            self._active = load_rules(default_rules_02(declared) if rules is None else rules, declared)
            return
        if rules is not None:
            raise IRValidationError("声明式规则仅适用于 IR 0.2 / 0.3")
        self.assertions.extend(derive_initial_assertions(self.doc["assertions"]))

    @classmethod
    def from_path(cls, path: str) -> "KnowledgeBase":
        with Path(path).open(encoding="utf-8") as handle:
            return cls(json.load(handle))

    def query(self, subject: str, relation: str, object_: str, context: str, valid_at: Optional[str] = None) -> Dict[str, Any]:
        if self._index is not None:
            from .query_preview import evaluate_query

            return evaluate_query(self._index, self._active, subject, relation, object_, context, valid_at)
        for value, name in [(subject, "subject"), (relation, "relation"), (object_, "object"), (context, "context")]:
            _nonempty_string(value, name)
        if valid_at is not None:
            _validate_day(valid_at, "查询 valid_at")
        matches = []
        target_roles = {"subject": subject, "relation": relation, "object": object_}
        for a in self.assertions:
            if a["roles"] == target_roles and a["context"] == context and a.get("valid_at") == valid_at:
                matches.append(Evidence(a["id"], a["polarity"], a["sources"], a.get("_derived_by"), a.get("_premises", ())))
        positive = [e for e in matches if e.polarity == "positive"]
        negative = [e for e in matches if e.polarity == "negative"]
        status = "冲突" if positive and negative else "支持" if positive else "反对" if negative else "未知"
        return {"status": status, "query": {**target_roles, "context": context, "valid_at": valid_at}, "evidence": [e.as_dict() for e in matches]}
