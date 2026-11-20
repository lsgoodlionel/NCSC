"""datasets/synthetic-v0 的一致性与可执行性检查。

每个条目的 IR 文档 = registry 的全部概念 + 条目自己的断言（version 0.2）。
期望答案按 IR 0.2 / P-3 方案 A 书写。0.2 的查询要等 #5 实现，在此之前：
把文档降为 0.1（只改 version）交给现行内核执行，逐条核对。
两种语义不同的查询（D1）在条目里给出 ir01 期望，用它核对现行行为。
"""

import copy
import json
import unittest
from pathlib import Path
from typing import Any, Dict, List

from ncsc import KnowledgeBase

try:
    import jsonschema
except ImportError:  # pragma: no cover - 取决于开发环境
    jsonschema = None

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "datasets" / "synthetic-v0"
REGISTRY: Dict[str, Any] = json.loads((DATA / "registry.json").read_text(encoding="utf-8"))
ITEMS: List[Dict[str, Any]] = json.loads((DATA / "items.json").read_text(encoding="utf-8"))["items"]
STATUSES = ("支持", "反对", "冲突", "未知")
REQUIRED_PHENOMENA = {
    "direct-positive", "explicit-negation", "absence-not-negation", "unknown-unrelated", "missing-premise", "negative-premise",
    "rule-r1", "rule-binding", "reported-cause", "reported-cause-no-upgrade", "modality-not-representable",
    "conflict-direct", "no-majority-vote", "premise-conflict", "time-partition", "time-no-merge",
    "context-partition", "context-no-conflict", "undated-partition",
}
NOT_ANNOTATED_REASONS = {"absence", "modality", "no-relation", "ambiguous"}  # 与 annotation/GUIDE.md §7 一致


def document(item: Dict[str, Any], version: str = "0.2") -> Dict[str, Any]:
    return {"version": version, "concepts": copy.deepcopy(REGISTRY["concepts"]), "assertions": copy.deepcopy(item["assertions"])}


def summarize(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for e in evidence:
        if "derived_by" in e:
            out.append({"derived_by": e["derived_by"], "premises": list(e["premises"])})
        else:
            out.append({"assertion_id": e["assertion_id"]})
    return out


class ConsistencyTests(unittest.TestCase):
    def test_ids_are_unique_and_prefixed(self) -> None:
        item_ids = [i["id"] for i in ITEMS]
        self.assertEqual(len(item_ids), len(set(item_ids)))
        seen = set()
        for item in ITEMS:
            code = "s" + item["id"].rsplit("-", 1)[1]
            with self.subTest(item=item["id"]):
                qids = [q["id"] for q in item["queries"]]
                self.assertEqual(len(qids), len(set(qids)))
                for a in item["assertions"]:
                    self.assertTrue(a["id"].startswith(f"a:{code}-"), a["id"])
                    self.assertNotIn(a["id"], seen)
                    seen.add(a["id"])

    def test_references_resolve_to_registry(self) -> None:
        concepts = {c["id"] for c in REGISTRY["concepts"]}
        sources = {s["id"]: s["description"] for s in REGISTRY["sources"]}
        contexts = {c["id"] for c in REGISTRY["contexts"]}
        for item in ITEMS:
            with self.subTest(item=item["id"]):
                self.assertTrue(item["text"].strip())
                for a in item["assertions"]:
                    self.assertIn(a["context"], contexts)
                    for s in a["sources"]:
                        self.assertEqual(s["description"], sources[s["id"]])
                for q in item["queries"]:
                    for role in ("subject", "relation", "object"):
                        self.assertIn(q["query"][role], concepts)
                    self.assertIn(q["query"]["context"], contexts)
                for n in item["not_annotated"]:
                    self.assertIn(n["reason"], NOT_ANNOTATED_REASONS)
                    self.assertIn(n["span"], item["text"])

    def test_expected_evidence_refers_to_item_assertions(self) -> None:
        for item in ITEMS:
            by_id = {a["id"]: a for a in item["assertions"]}
            for q in item["queries"]:
                with self.subTest(item=item["id"], query=q["id"]):
                    expect = q["expect"]
                    self.assertIn(expect["status"], STATUSES)
                    groups = [e.get("premises", [e.get("assertion_id")]) for e in expect["evidence"]] + expect["suppressed"]
                    for group in groups:
                        for aid in group:
                            self.assertIn(aid, by_id)
                    if expect["status"] == "未知":
                        self.assertEqual(expect["evidence"], [])
                    # P-4 §5：原始断言按 ID 升序在前，推导证据（d: ID）在后
                    base = [e["assertion_id"] for e in expect["evidence"] if "assertion_id" in e]
                    self.assertEqual(base, sorted(base))
                    kinds = ["a" if "assertion_id" in e else "d" for e in expect["evidence"]]
                    self.assertEqual(kinds, sorted(kinds))

    def test_coverage(self) -> None:
        statuses = [q["expect"]["status"] for i in ITEMS for q in i["queries"]]
        for status in STATUSES:
            with self.subTest(status=status):
                self.assertGreaterEqual(statuses.count(status), 2)
        phenomena = {p for i in ITEMS for q in i["queries"] for p in q["phenomena"]}
        self.assertEqual(REQUIRED_PHENOMENA - phenomena, set())
        self.assertEqual(phenomena - REQUIRED_PHENOMENA, set(), "新增现象标签请登记到 REQUIRED_PHENOMENA 与标注指南")

    def test_reported_cause_is_never_a_rule_premise(self) -> None:
        for item in ITEMS:
            causes = {a["id"] for a in item["assertions"] if a["roles"]["relation"] == "r:claim:reported-cause"}
            for q in item["queries"]:
                for e in q["expect"]["evidence"]:
                    with self.subTest(item=item["id"], query=q["id"]):
                        self.assertFalse(causes & set(e.get("premises", [])))


@unittest.skipIf(jsonschema is None, "未安装 jsonschema；运行 pip install -e \".[dev]\"")
class StructuralTests(unittest.TestCase):
    def test_item_documents_match_ir_02_schema(self) -> None:
        schema = json.loads((ROOT / "schema" / "ir-0.2.draft.schema.json").read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for item in ITEMS:
            with self.subTest(item=item["id"]):
                errors = list(validator.iter_errors(document(item)))
                self.assertEqual(errors, [], [e.message for e in errors][:3])


class ExecutableTests(unittest.TestCase):
    def test_expected_answers_against_current_kernel(self) -> None:
        for item in ITEMS:
            kb = KnowledgeBase(document(item, "0.1"))
            for q in item["queries"]:
                with self.subTest(item=item["id"], query=q["id"]):
                    s = q["query"]
                    result = kb.query(s["subject"], s["relation"], s["object"], s["context"], s["valid_at"])
                    if "ir01" in q:
                        self.assertEqual(result["status"], q["ir01"]["status"])
                        self.assertNotEqual(q["ir01"]["status"], q["expect"]["status"])
                        continue
                    self.assertEqual(result["status"], q["expect"]["status"])
                    # 0.1 按文档顺序输出，0.2 按 ID 排序（P-4 §5），所以这里按集合比较
                    key = lambda e: json.dumps(e, sort_keys=True, ensure_ascii=False)  # noqa: E731
                    self.assertEqual(sorted(map(key, summarize(result["evidence"]))), sorted(map(key, q["expect"]["evidence"])))
                    self.assertEqual(q["expect"]["suppressed"], [], "只有 D1 类查询会有被抑制推导")


if __name__ == "__main__":
    unittest.main()
