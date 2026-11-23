import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from adapters.ollama import extract
from eval.extraction import predict, score, validate_batch


class LocalExtractionTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.registry = json.loads((root / "datasets/synthetic-v0/registry.json").read_text(encoding="utf8"))
        self.text = "Alpha 项目看板称发布已完成。"
        self.claim = dict(id="a:one", roles=dict(subject="c:task:release", relation="r:status:completed",
                                                 object="c:value:true"), context="ctx:project-alpha",
                          polarity="positive", sources=[dict(id="src:excerpt", description=self.text)])
        self.packet = [{"id": "p", "text": self.text}]
        self.sources = {"src:excerpt": self.text}

    @patch("adapters.ollama.http.client.HTTPConnection")
    def test_opt_in_and_configuration(self, connect):
        with patch.dict(os.environ, {}, clear=True):
            args = dict(sources=self.sources, registry=self.registry)
            self.assertEqual(extract(self.text, "0.2", **args), {"status": "disabled"})
            self.assertEqual(extract(self.text, "0.2", enabled=True, **args)["status"], "invalid_config")
            with patch.dict(os.environ, {"NCSC_OLLAMA_MODEL":"local", "NCSC_OLLAMA_REQUIRE_TOKEN":"1"}):
                result = extract(self.text, "0.2", enabled=True, **args)
                self.assertIn("NCSC_OLLAMA_TOKEN", result["error"])
        connect.assert_not_called()

    @patch("adapters.ollama.http.client.HTTPConnection")
    def test_fake_provider_request_and_failure(self, connect):
        def response(claim):
            env = {"done": True, "response": json.dumps({"assertions": [claim]})}
            data = io.BytesIO(json.dumps(env).encode())
            data.status = 200
            return data
        conn = connect.return_value
        conn.getresponse.side_effect = [response(self.claim), response(dict(self.claim, sources=[])), OSError()]
        with patch.dict(os.environ, {"NCSC_OLLAMA_MODEL":"stub", "NCSC_OLLAMA_PORT":"11435"}, clear=True):
            statuses = [predict(self.packet, self.registry, enabled=True)[0]["status"] for _ in range(3)]
        self.assertEqual(statuses, ["candidate", "invalid_candidate", "provider_error"])
        self.assertEqual(conn.request.call_count, 3)
        connect.assert_called_with("127.0.0.1", 11435, timeout=120)
        method, path = conn.request.call_args.args
        self.assertEqual((method, path), ("POST", "/api/generate"))
        request = json.loads(conn.request.call_args.kwargs["body"])
        self.assertFalse(request["stream"])
        prompt = json.loads(request["prompt"])
        self.assertEqual(prompt["source_excerpts"], self.sources)
        self.assertNotIn("assertions", prompt)

    def test_blind_import_and_scoring_denominators(self):
        refs = [{"id": "p", "assertions": [self.claim]}, {"id":"q", "assertions":[self.claim]}]
        p = validate_batch(self.packet, self.registry, [{"id":"p","assertions":[self.claim, dict(self.claim,id="a:two")]}])
        report = score(refs, p + [{"id":"q","status":"invalid_candidate"}])
        self.assertEqual((report["matched"], report["predicted"], report["expected"]), (1,1,2))
        self.assertEqual((report["precision"], report["recall"]), (1,0.5))
        self.assertIsNone(score([{"id":"p","assertions":[]}], [{"id":"p","status":"provider_error"}])["recall"])
        with self.assertRaises(ValueError):
            score(refs, p)
        with self.assertRaisesRegex(ValueError, "盲包"):
            validate_batch([dict(self.packet[0], expect="private")], self.registry, refs[:1])
        invalid = validate_batch(self.packet, self.registry, [{"id":"p","assertions":[dict(self.claim,
                    sources=[{"id":"src:excerpt","description":"猜测"}])]}])
        self.assertEqual(invalid[0]["status"], "invalid_candidate")
