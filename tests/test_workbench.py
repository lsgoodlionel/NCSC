import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from workbench.mcp_tool import dispatch
from workbench.server import execute

ROOT = Path(__file__).resolve().parents[1]


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.request = {"document": json.loads((ROOT/"examples/release-readiness.json").read_text(encoding="utf8")),
                        "program": "query", "query": {"subject":"c:task:release","relation":"r:status:blocked",
                        "object":"c:value:true","context":"ctx:project-alpha","day":"2026-11-19"}}

    def test_all_programs(self):
        events = []
        self.assertEqual(execute(self.request, events.append)["status"], "支持")
        self.assertEqual([e["kind"] for e in events], ["start", "done"] * 3)
        self.request["program"] = "optimize"
        result = execute(self.request, events.append)
        self.assertTrue(result["verified"])
        self.assertEqual([d["status"] for d in result["days"]], ["支持", "未知", "冲突", "反对"])
        self.request["program"] = "validate"
        self.assertTrue(execute(self.request, events.append)["valid"])

    def test_mcp_only_records_real_query(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder)/"receipt"
            def call(args):
                return dispatch({"id":1,"method":"tools/call","params":{"name":"query","arguments":args}},
                                self.request,receipt)
            self.assertIn("error",call({"day":"2026-11-20"}))
            self.assertFalse(receipt.exists())
            result = call({})["result"]["content"][0]["text"]
            self.assertEqual(json.loads(result)["status"],"支持")
            self.assertEqual(len(receipt.read_text()),64)

    def test_no_tool_receipt_no_verified_badge(self):
        with patch("workbench.server.explain", return_value={"session":None,"model_text":"自由回答"}):
            self.assertFalse(execute(dict(self.request, engine="codex"), lambda _:None)["verified"])
        with self.assertRaisesRegex(ValueError,"会话"):
            execute(dict(self.request, engine="codex", session="outside-session"), lambda _:None)
