"""IR 契约测试：结构层（JSON Schema）与内核层（Python 校验器）对同一组夹具分别判定。

夹具与判例由 manifest.json 登记。layer 决定两层的期望：
  valid        结构层通过，内核接受
  structural   结构层拒绝，内核拒绝
  value        结构层通过，内核拒绝（如日历无效）
  referential  结构层通过，内核拒绝（重复 ID、悬空引用等）

kernel 字段：
  enforced            内核必须符合期望
  pending:<ref>       已知差异：内核当前不符合；一旦符合即失败，提醒在修复 PR 中改为 enforced
  unimplemented:<ref> 内核尚未实现该版本或语义，跳过
  rejected            被否决的备选方案，只作文档，跳过

结构层需要 jsonschema（开发依赖）；未安装时跳过结构层用例。
"""

import json
import unittest
from pathlib import Path
from typing import Any, Dict

from ncsc import IRValidationError, KnowledgeBase
from ncsc.core import validate_document

try:
    import jsonschema
except ImportError:  # pragma: no cover - 取决于开发环境
    jsonschema = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST: Dict[str, Any] = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
LAYERS = {"valid": (True, True), "structural": (False, False), "value": (True, False), "referential": (True, False)}


def _load(rel: str) -> Any:
    return json.loads((HERE / rel).read_text(encoding="utf-8"))


def _schema(name: str) -> Dict[str, Any]:
    return json.loads((ROOT / "schema" / name).read_text(encoding="utf-8"))


def _kernel_accepts(doc: Any) -> bool:
    try:
        validate_document(doc)
    except IRValidationError:
        return False
    return True


def _evidence_summary(result: Dict[str, Any]) -> list:
    keys = ("assertion_id", "polarity", "derived_by", "premises")
    return [{k: e[k] for k in keys if k in e} for e in result["evidence"]]


class ManifestTests(unittest.TestCase):
    def test_every_fixture_file_is_registered(self) -> None:
        on_disk = {p.relative_to(HERE).as_posix() for p in (HERE / "fixtures").rglob("*.json")}
        registered = {f["path"] for f in MANIFEST["fixtures"]}
        self.assertEqual(on_disk, registered)
        cases = {p.relative_to(HERE).as_posix() for p in (HERE / "cases").rglob("*.json")}
        self.assertEqual(cases, set(MANIFEST["query_cases"]))

    def test_layer_matches_directory(self) -> None:
        for f in MANIFEST["fixtures"]:
            with self.subTest(path=f["path"]):
                self.assertEqual(f["path"].split("/")[1:3], [f["ir"], f["layer"]])
                self.assertIn(f["layer"], LAYERS)

    def test_example_regression_fixture_matches_example(self) -> None:
        frozen = _load("fixtures/0.1/valid/example-regression.json")
        example = json.loads((ROOT / "examples" / "project_state.json").read_text(encoding="utf-8"))
        self.assertEqual(frozen, example, "示例已改动：若属预期，请同时更新回归夹具并说明契约影响")


@unittest.skipIf(jsonschema is None, "未安装 jsonschema；运行 pip install -e \".[dev]\"")
class StructuralLayerTests(unittest.TestCase):
    def test_schemas_are_valid_2020_12(self) -> None:
        names = list(MANIFEST["schemas"].values()) + [MANIFEST["query_result_schema"]]
        for name in names:
            with self.subTest(schema=name):
                jsonschema.Draft202012Validator.check_schema(_schema(name))

    def test_fixtures_against_schema(self) -> None:
        for f in MANIFEST["fixtures"]:
            with self.subTest(path=f["path"]):
                validator = jsonschema.Draft202012Validator(_schema(MANIFEST["schemas"][f["ir"]]))
                errors = list(validator.iter_errors(_load(f["path"])))
                expected_valid = LAYERS[f["layer"]][0]
                self.assertEqual(not errors, expected_valid, [e.message for e in errors][:3])

    def test_proposed_query_results_against_schema(self) -> None:
        """判例中任何带完整 result 的期望（p3-option-a、p6 等）都须符合查询结果 Schema。"""
        validator = jsonschema.Draft202012Validator(_schema(MANIFEST["query_result_schema"]))
        for rel in MANIFEST["query_cases"]:
            for item in _load(rel)["queries"]:
                for key, expect in item["expect"].items():
                    if "result" not in expect:
                        continue
                    with self.subTest(case=rel, query=item["name"], expect=key):
                        result = expect["result"]
                        errors = list(validator.iter_errors(result))
                        self.assertEqual(errors, [], [e.message for e in errors][:3])
                        self.assertEqual(result["query"], item["query"])
                        # P-4 §5：证据与被抑制推导按 ID 的码位升序排列，与输入顺序无关
                        ids = [e["assertion_id"] for e in result["evidence"]]
                        self.assertEqual(ids, sorted(ids))
                        keys = [s["premises"] for s in result["suppressed"]]
                        self.assertEqual(keys, sorted(keys))


class KernelLayerTests(unittest.TestCase):
    def test_fixtures_against_kernel(self) -> None:
        for f in MANIFEST["fixtures"]:
            with self.subTest(path=f["path"]):
                mode = f["kernel"]
                if mode.startswith("unimplemented:"):
                    self.skipTest(mode)
                expected = LAYERS[f["layer"]][1]
                actual = _kernel_accepts(_load(f["path"]))
                if mode.startswith("pending:"):
                    if actual == expected:
                        self.fail(f"{mode} 已被修复：请把 manifest 中该夹具改为 enforced")
                    self.skipTest(f"已知差异 {mode}")
                self.assertEqual(mode, "enforced")
                self.assertEqual(actual, expected)

    def test_query_cases_current_behaviour(self) -> None:
        for rel in MANIFEST["query_cases"]:
            case = _load(rel)
            if case["document"]["version"] != "0.1":
                continue  # 0.2 起的判例只有提议期望，等内核实现后再执行
            kb = KnowledgeBase(case["document"])
            for item in case["queries"]:
                expect = item["expect"]["ir-0.1-current"]
                with self.subTest(case=case["id"], query=item["name"]):
                    self.assertEqual(expect["kernel"], "enforced")
                    q = item["query"]
                    result = kb.query(q["subject"], q["relation"], q["object"], q["context"], q["valid_at"])
                    self.assertEqual(result["status"], expect["status"])
                    self.assertEqual(_evidence_summary(result), expect["evidence"])


if __name__ == "__main__":
    unittest.main()
