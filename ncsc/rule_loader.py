"""加载 P-4 声明式规则。调用方提供该文档或登记表中已声明的概念 ID。"""
import re
from copy import deepcopy
from typing import AbstractSet, Any, Dict, Iterable, List, Set

from .core import IRValidationError, _check_id, _check_text, _exact_keys, _nonempty_string


def _pattern_variables(pattern: Any, where: str, declared: AbstractSet[str], conclusion: bool) -> Set[str]:
    if not isinstance(pattern, dict):
        raise IRValidationError(f"{where}: 预期三元组模式")
    keys = {"subject", "relation", "object", "polarity"}
    _exact_keys(pattern, keys, where, keys)
    allowed = ("positive",) if conclusion else ("positive", "negative")
    if pattern["polarity"] not in allowed:
        raise IRValidationError(f"{where}.polarity: 极性不合法")
    variables = set()
    for slot in ("subject", "relation", "object"):
        path = f"{where}.{slot}"
        term = _nonempty_string(pattern[slot], path)
        if slot != "relation" and re.fullmatch(r"\?[a-z][a-z0-9_]{0,31}", term):
            variables.add(term)
            continue
        _check_id(term, "r" if slot == "relation" else "c", path)
        if term == "r:claim:reported-cause" or term not in declared:
            raise IRValidationError(f"{path}: 禁用或未登记的常量 {term}")
    return variables


def load_rules(documents: Iterable[Any], declared: AbstractSet[str]) -> List[Dict[str, Any]]:
    """整组通过校验后返回 active 规则的独立副本，按规则 ID 排序。"""
    active: Dict[str, Dict[str, Any]] = {}
    negative_relations: Set[str] = set()
    outputs: Set[str] = set()
    for i, rule in enumerate(documents):
        where = f"rules[{i}]"
        if not isinstance(rule, dict):
            raise IRValidationError(f"{where}: 预期规则对象")
        keys = {"format", "id", "status", "description", "premises", "conclusion"}
        _exact_keys(rule, keys, where, keys)
        if rule["format"] != "ncsc-rules/0.2" or rule["status"] not in ("proposed", "active", "retired"):
            raise IRValidationError(f"{where}: 非法规则格式或状态")
        rid = _nonempty_string(rule["id"], f"{where}.id")
        if not re.fullmatch("[a-z][a-z0-9_]{0,62}", rid):
            raise IRValidationError(f"{where}.id: 非法规则 ID")
        _check_text(_nonempty_string(rule["description"], f"{where}.description"), f"{where}.description")
        premises = rule["premises"]
        if not isinstance(premises, list) or not 1 <= len(premises) <= 4:
            raise IRValidationError(f"{where}.premises: 需要 1–4 个前提")
        bound: Set[str] = set()
        for j, premise in enumerate(premises):
            bound.update(_pattern_variables(premise, f"{where}.premises[{j}]", declared, False))
        needed = _pattern_variables(rule["conclusion"], f"{where}.conclusion", declared, True)
        if needed - bound:
            raise IRValidationError(f"{where}.conclusion: 未绑定变量 {sorted(needed - bound)}")
        if rule["status"] == "active":
            if rid in active:
                raise IRValidationError(f"{where}.id: 重复 active 规则 {rid}")
            active[rid] = deepcopy(rule)
            outputs.add(rule["conclusion"]["relation"])
            negative_relations.update(p["relation"] for p in premises if p["polarity"] == "negative")
    clashes = negative_relations & outputs
    if clashes:
        raise IRValidationError(f"负向前提引用可推导关系: {sorted(clashes)}")
    return [active[rid] for rid in sorted(active)]
