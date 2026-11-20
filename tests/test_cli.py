import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from ncsc.cli import main


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = str(ROOT / "examples" / "project_state.json")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "ncsc.cli", *args],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=15,
    )


def call_main(*args: str) -> subprocess.CompletedProcess[str]:
    stdout, stderr = StringIO(), StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(args)
    return subprocess.CompletedProcess(args, code, stdout.getvalue(), stderr.getvalue())


class CLITests(unittest.TestCase):
    def test_validate_example(self) -> None:
        result = run_cli("validate", EXAMPLE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), {"valid": True, "version": "0.1"})

    def test_query_explains_derived_result(self) -> None:
        result = call_main(
            "query", EXAMPLE,
            "--subject", "c:task:release",
            "--relation", "r:status:blocked",
            "--object", "c:value:true",
            "--context", "ctx:project-alpha",
            "--valid-at", "2026-11-19",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        answer = json.loads(result.stdout)
        self.assertEqual(answer["status"], "支持")
        self.assertEqual(answer["evidence"][0]["derived_by"], "resource_unavailable_blocks_task")
        self.assertEqual(answer["evidence"][0]["premises"], ["a:release-requires-key", "a:key-unavailable"])

    def test_regression_d7_invalid_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "invalid.json"
            path.write_bytes(b"\xff")
            result = call_main("validate", str(path))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        error = json.loads(result.stderr)
        self.assertIs(error["valid"], False)
        self.assertIn("utf-8", error["error"].lower())

    def test_cli_date_typo_is_a_validation_error(self) -> None:
        result = run_cli("query", EXAMPLE, "--subject", "c:task:release",
                         "--relation", "r:status:blocked", "--object", "c:value:true",
                         "--context", "ctx:project-alpha", "--valid-at", "2026-1-5")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("valid_at", json.loads(result.stderr)["error"])

    def test_ir02_query_matches_d1_and_explicit_rule_replaces_default(self) -> None:
        case = json.loads((ROOT / "tests/contract/cases/d1-control-no-conflict.json").read_text(encoding="utf-8"))["queries"][0]
        fixture = ROOT / "tests/contract/fixtures"
        args = ["query", str(fixture / "0.2/valid/example-migrated.json")]
        for key, val in case["query"].items():
            args.extend(["--" + key.replace("_", "-"), val])
        expected = case["expect"]["p3-option-a"]["result"]
        result = run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
        r1 = json.loads((fixture / "rules-0.2/valid/r1-resource-unavailable.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            retired = Path(tmp) / "retired.json"
            retired.write_text(json.dumps(dict(r1, status="retired")))
            result = run_cli(*args, "--rule", str(retired))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["reason"], "no_evidence")

    def test_ir02_suppressed_derived_premise_retains_proof_ids(self) -> None:
        from ncsc import KnowledgeBase

        fixtures = ROOT / "tests/contract/fixtures"
        doc = json.loads((fixtures / "0.2/valid/example-migrated.json").read_text(encoding="utf-8"))
        r1 = json.loads((fixtures / "rules-0.2/valid/r1-resource-unavailable.json").read_text(encoding="utf-8"))
        query = ("c:task:release", "r:status:blocked", "c:value:true", "ctx:project-alpha", "2026-11-19")
        proof_id = KnowledgeBase(doc).query(*query)["evidence"][0]["assertion_id"]
        doc["concepts"].append({"id": "r:delayed", "kind": "relation", "aliases": ["延期"]})
        negative = dict(doc["assertions"][0], id="a:clear", polarity="negative",
                        roles={"subject": query[0], "relation": query[1], "object": query[2]})
        doc["assertions"].append(negative)
        second = dict(r1, id="delay", premises=[r1["conclusion"]],
                      conclusion=dict(r1["conclusion"], relation="r:delayed"))
        answer = KnowledgeBase(doc, [r1, second]).query(query[0], "r:delayed", *query[2:])
        self.assertEqual(answer["reason"], "premise_conflict")
        self.assertEqual(answer["suppressed"], [
            {"rule_id": "delay", "premises": [proof_id], "reason": "premise_conflict",
             "contested_premises": [{"assertion_id": proof_id, "opposing": ["a:clear"]}]}
        ])
        doc["assertions"].reverse()
        self.assertEqual(KnowledgeBase(doc, [second, r1]).query(query[0], "r:delayed", *query[2:]), answer)

    def test_regular_query_preserves_large_legacy_input(self) -> None:
        from unittest.mock import patch
        from ncsc import preview_io

        query = ["--subject", "c:task:release", "--relation", "r:status:blocked", "--object", "c:value:true",
                 "--context", "ctx:project-alpha", "--valid-at", "2026-11-19"]
        fixture = ROOT / "tests/contract/fixtures/0.2/valid/example-migrated.json"
        with patch.object(preview_io, "IR_BYTES", 1):
            self.assertEqual(call_main("query", EXAMPLE, *query).returncode, 0)
            result = call_main("query", str(fixture), *query)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stderr)["resource"], "ir_bytes")
