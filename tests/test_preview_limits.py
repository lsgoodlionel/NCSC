import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ncsc import preview_io
from ncsc.cli import main
from ncsc.query_preview import QueryLimitError, _JoinBudget


class PreviewLimits(unittest.TestCase):
    def test_exact_input_boundary_and_accumulated_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "doc"
            rule = Path(folder) / "rule"
            doc.write_bytes(b"null")
            rule.write_bytes(b"{}")
            with patch.multiple(preview_io, IR_BYTES=4, RULE_BYTES=2, RULE_SET_BYTES=4):
                self.assertEqual(preview_io.load_inputs(str(doc), [str(rule)] * 2), (None, [{}, {}]))
                with self.assertRaisesRegex(QueryLimitError, "rule_set_bytes"):
                    preview_io.load_inputs(str(doc), [str(rule)] * 3)
                rule.write_bytes(b"bad")
                with self.assertRaisesRegex(QueryLimitError, "rule_bytes"):
                    preview_io.load_inputs(str(doc), [str(rule)])
                doc.write_bytes(b"xxxxx")
                with self.assertRaisesRegex(QueryLimitError, "ir_bytes"):
                    preview_io.load_inputs(str(doc), [])

    def test_wire_size_counts_utf8_and_newline(self):
        expected = '"汉字"\n'.encode()
        with patch.object(preview_io, "OUTPUT_BYTES", len(expected)):
            self.assertEqual(preview_io.encode_response("汉字"), expected)
        with patch.object(preview_io, "OUTPUT_BYTES", len(expected) - 1):
            with self.assertRaisesRegex(QueryLimitError, "output_bytes"):
                preview_io.encode_response("汉字")

    def test_join_counters_accept_last_unit(self):
        for method, name in [("attempt", "MAX_JOIN_ATTEMPTS"), ("retain", "MAX_JOIN_ROWS")]:
            with patch("ncsc.query_preview." + name, 2):
                charge = getattr(_JoinBudget(), method)
                charge()
                charge()
                with self.assertRaises(QueryLimitError):
                    charge()

    def test_cli_reports_limits_without_partial_output(self):
        root = Path(__file__).resolve().parents[1] / "tests/contract/fixtures"
        args = ["query-preview", str(root / "0.2/valid/example-migrated.json"),
                "--subject", "c:task:release", "--relation", "r:status:blocked",
                "--object", "c:value:true", "--context", "ctx:project-alpha", "--valid-at", "2026-11-19",
                "--rule", str(root / "rules-0.2/valid/r1-resource-unavailable.json")]
        for field, key in [("ncsc.query_preview.MAX_JOIN_ATTEMPTS", "join_attempts"),
                           ("ncsc.query_preview.MAX_JOIN_ROWS", "join_rows"),
                           ("ncsc.preview_io.OUTPUT_BYTES", "output_bytes"),
                           ("ncsc.preview_io.IR_BYTES", "ir_bytes"),
                           ("ncsc.preview_io.RULE_BYTES", "rule_bytes"),
                           ("ncsc.preview_io.RULE_SET_BYTES", "rule_set_bytes")]:
            with self.subTest(field=field), patch(field, 1):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(main(args), 3)
                self.assertEqual(out.getvalue(), "")
                self.assertEqual(json.loads(err.getvalue()), {"error": "query_limit_exceeded",
                                                             "resource": key, "limit": 1})
