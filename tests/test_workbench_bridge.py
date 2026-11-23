import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from workbench import codex_bridge as bridge


class BridgeTests(unittest.TestCase):
    def run_fixture(self, events, session=None):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "codex"
            script.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdin.read()\n"
                              + "\n".join("print(" + repr(json.dumps(e)) + ")" for e in events))
            script.chmod(0o700)
            with patch.object(bridge, "find_codex", return_value=str(script)):
                log = []
                value = bridge.explain({}, "解释", session, log.append,
                                       snapshot_path=script, receipt_path=Path(tmp) / "receipt")
                return value, log

    @unittest.skipUnless(bridge.os.name == "posix", "POSIX executable fixture")
    def test_public_reply_only(self):
        sid = str(uuid4())
        result, log = self.run_fixture([
            {"type": "thread.started", "thread_id": sid}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "reasoning", "text": "private"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "公开答复"}},
            {"type": "turn.completed"}], sid)
        self.assertEqual(result, {"session": sid, "model_text": "公开答复"})
        self.assertNotIn("private", repr(log))

    def test_absent_cli(self):
        with patch.object(bridge, "find_codex", return_value=None), self.assertRaises(ValueError):
            bridge.explain({}, "", None, list().append, snapshot_path="", receipt_path="")
