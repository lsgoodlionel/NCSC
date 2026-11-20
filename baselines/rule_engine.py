"""用 SQLite 连接和有限事实闭包解释 IR 0.2 合成集上的声明式规则。"""

import argparse
from collections import defaultdict
from contextlib import closing
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import re
import sqlite3

from .json_exact import ROLES, STATUS


def _atom(subject, relation, obj, polarity="positive"):
    return dict(subject=subject, relation=relation, object=obj, polarity=polarity)


R1 = {
    "format": "ncsc-rules/0.2", "id": "resource_unavailable_blocks_task",
    "status": "active", "description": "任务需要不可用的资源时推导阻塞",
    "premises": [_atom("?task", "r:task:requires", "?resource"),
                 _atom("?resource", "r:resource:unavailable", "c:value:true")],
    "conclusion": _atom("?task", "r:status:blocked", "c:value:true"),
}
FIELDS = (*ROLES, "polarity")
VAR = re.compile(r"\?[a-z][a-z0-9_]{0,31}")
CONSTANT = re.compile(r"[cr]:[a-z0-9](?:[a-z0-9._:-]{0,126}[a-z0-9])?")


def _compile(rule):
    """将正文编译成自连接；输入常量始终用参数绑定，列名只来自 FIELDS。"""
    aliases, filters, bindings, params = [], [], {}, {}

    def literal(value):
        key = f"v{len(params)}"
        params[key] = value
        return ":" + key

    def term_sql(term, field, column=None):
        if not isinstance(term, str):
            raise ValueError("规则项必须为字符串")
        if field in ("subject", "object") and VAR.fullmatch(term):
            if term not in bindings:
                if column is None:
                    raise ValueError("结论变量必须由前提绑定")
                bindings[term] = column
            return bindings[term]
        if field == "polarity":
            if term not in ("positive", "negative"):
                raise ValueError("前提需要明确正负极性")
        elif (not CONSTANT.fullmatch(term) or term[0] != ("r" if field == "relation" else "c")
              or term == "r:claim:reported-cause"):
            raise ValueError(f"不支持的规则常量 {term}")
        return literal(term)

    patterns = rule["premises"]
    if not isinstance(patterns, list) or not 1 <= len(patterns) <= 4:
        raise ValueError("每条规则需要 1–4 个前提")
    for i, atom in enumerate(patterns):
        if not isinstance(atom, dict) or set(atom) != set(FIELDS):
            raise ValueError("无效的规则前提")
        alias = f"p{i}"
        aliases.append(alias)
        for field in FIELDS:
            column = f"{alias}.{field}"
            value = term_sql(atom[field], field, column)
            if value != column:
                filters.append(f"{column} = {value}")
        same_roles = " AND ".join(f"opp.{f} = {alias}.{f}" for f in ROLES)
        filters.append(f"NOT EXISTS (SELECT 1 FROM facts opp WHERE {same_roles} AND opp.polarity != {alias}.polarity)")
    head = rule["conclusion"]
    if not isinstance(head, dict) or set(head) != set(FIELDS) or head["polarity"] != "positive":
        raise ValueError("需要正向、完整的规则结论")
    columns = [term_sql(head[f], f) + " AS " + f for f in FIELDS] + [a + ".rowid" for a in aliases]
    sources = ", ".join("facts " + a for a in aliases)
    sql = f"SELECT {', '.join(columns)} FROM {sources} WHERE {' AND '.join(filters)}"
    return sql, params


def _rules(documents):
    active, negative, heads = {}, set(), set()
    for rule in documents:
        if not isinstance(rule, dict) or set(rule) != set(R1):
            raise ValueError("不支持的规则结构")
        rid = rule["id"]
        if not isinstance(rid, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", rid):
            raise ValueError("无效的规则 ID")
        if rule["format"] != "ncsc-rules/0.2" or rule["status"] not in ("active", "proposed", "retired"):
            raise ValueError("不支持的规则格式或状态")
        query = _compile(rule)
        if rule["status"] == "active":
            if rid in active:
                raise ValueError(f"重复启用的规则 {rid}")
            active[rid] = query
            heads.add(rule["conclusion"]["relation"])
            negative.update(p["relation"] for p in rule["premises"] if p["polarity"] == "negative")
    if negative & heads:
        raise ValueError("负向前提只允许引用没有规则可推出的关系")
    return active


def _close(assertions, rules):
    """只把四元事实送回连接；同一事实的所有输入来源独立保存在 originals。"""
    originals = defaultdict(list)
    for a in assertions:
        fact = (*(a["roles"][field] for field in ROLES), a["polarity"])
        originals[fact].append(a["id"])
    insert = "INSERT OR IGNORE INTO facts VALUES (?, ?, ?, ?)"
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE facts(subject, relation, object, polarity, UNIQUE(subject,relation,object,polarity))")
        db.executemany(insert, originals.keys())
        while True:
            before = db.total_changes
            for sql, params in rules.values():
                db.execute(f"INSERT OR IGNORE INTO facts SELECT subject,relation,object,polarity FROM ({sql})", params)
            if before == db.total_changes:
                break
        facts = {row[0]: row[1:] for row in db.execute("SELECT rowid,* FROM facts")}
        edges = defaultdict(list)
        for rid, (sql, params) in rules.items():
            for row in db.execute(sql, params):
                edges[row[:4]].append((rid, tuple(facts[key] for key in row[4:])))
    return originals, edges


def _child_id(node):
    if "assertion_id" in node:
        return node["assertion_id"]
    encoded = json.dumps([node["derived_by"], node["premises"]], ensure_ascii=False, separators=(",", ":"))
    return "b:" + sha256(encoded.encode("utf-8")).hexdigest()


def _proofs(fact, originals, edges, path):
    if fact in path:
        return []
    direct = [{"assertion_id": aid, "polarity": fact[3]} for aid in sorted(originals.get(fact, ()))]
    inferred = []
    for rid, premises in edges.get(fact, ()):
        options = [_proofs(p, originals, edges, path | {fact}) for p in premises]
        for children in product(*options):
            ids = [_child_id(child) for child in children]
            node = {"derived_by": rid, "premises": ids, "polarity": "positive"}
            if any("derived_by" in entry for entry in children):
                node["trace"] = [dict(entry, assertion_id=aid) for entry, aid in zip(children, ids)]
            inferred.append(node)
    return direct + sorted(inferred, key=lambda node: (node["derived_by"], node["premises"]))


def predictions(dataset, rules=None):
    if dataset["ir_version"] != "0.2":
        raise ValueError("规则基线仅支持 IR 0.2")
    compiled = _rules([R1] if rules is None else rules)
    for item in dataset["items"]:
        partitions = defaultdict(list)
        for assertion in item["assertions"]:
            if "valid_during" in assertion:
                raise ValueError("IR 0.2 不支持 valid_during")
            partitions[assertion["context"], assertion.get("valid_at")].append(assertion)
        closures = {}
        for record in item["queries"]:
            query = record["query"]
            key = query["context"], query["valid_at"]
            if key not in closures:
                closures[key] = _close(partitions[key], compiled)
            originals, edges = closures[key]
            fact = tuple(query[f] for f in ROLES)
            evidence = []
            for sign in ("positive", "negative"):
                evidence.extend(_proofs((*fact, sign), originals, edges, set()))
            evidence.sort(key=lambda e: (0, e["assertion_id"]) if "assertion_id" in e
                          else (1, e["derived_by"], e["premises"]))
            yield {"item_id": item["id"], "query_id": record["id"],
                   "status": STATUS[frozenset(e["polarity"] for e in evidence)], "evidence": evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items", type=Path, help="synthetic-v0 的 items.json 路径")
    parser.add_argument("--rule", action="append", type=Path, help="完整替换默认 R1 的规则，可重复")
    args = parser.parse_args()
    try:
        rules = None if args.rule is None else [json.loads(p.read_text(encoding="utf-8")) for p in args.rule]
        rows = list(predictions(json.loads(args.items.read_text(encoding="utf-8")), rules))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"无法读取基线数据：{exc}\n")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
