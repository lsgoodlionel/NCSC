import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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


class CLITests(unittest.TestCase):
    def test_validate_example(self) -> None:
        result = run_cli("validate", EXAMPLE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), {"valid": True, "version": "0.1"})

    def test_query_explains_derived_result(self) -> None:
        result = run_cli(
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
            result = run_cli("validate", str(path))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        error = json.loads(result.stderr)
        self.assertIs(error["valid"], False)
        self.assertIn("utf-8", error["error"].lower())
