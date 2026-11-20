"""IR 0.3 区间查询和版本边界的命令行验收。"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def invoke(*args):
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "ncsc.cli", *args],
                          cwd=ROOT, capture_output=True, encoding="utf-8", timeout=15)


class IntervalCLITests(unittest.TestCase):
    def test_interrupted_rule_and_version_boundary(self):
        fixture = ROOT / "tests/contract/cases/p6-interrupted-rule.json"
        case = json.loads(fixture.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            for version in ("0.1", "0.2", "0.3"):
                with self.subTest(version=version):
                    document = dict(case["document"], version=version)
                    path.write_text(json.dumps(document), encoding="utf-8")
                    result = invoke("validate", str(path))
                    if version == "0.3":
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(json.loads(result.stdout), {"valid": True, "version": "0.3"})
                    else:
                        self.assertEqual(result.returncode, 2)
                        self.assertEqual(result.stdout, "")
                        self.assertIn("valid_during", json.loads(result.stderr)["error"])
            for query in case["queries"]:
                with self.subTest(day=query["query"]["valid_at"]):
                    args = ["query", str(path)]
                    for key, value in query["query"].items():
                        args.extend(["--" + key.replace("_", "-"), value])
                    result = invoke(*args)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), query["expect"]["p6"]["result"])
