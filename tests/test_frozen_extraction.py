from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from annotation import verify_ai_freeze as freeze
from eval.frozen_extraction import score_frozen


class FrozenExtractionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        data = root / "datasets/synthetic-v0"
        data.mkdir(parents=True)
        self.item = {"id": "demo", "text": "纯工程示例。"}
        self.reg = {"ir_version":"0.2","document_year":2026,"contexts":[{"id":"ctx:abc"}],
                    "concepts":[{"id":"c:x","kind":"entity","aliases":["甲"]},
                                {"id":"r:x","kind":"relation","aliases":["关系"]}]}
        paths = {"datasets/synthetic-v0/items.json":{"items":[dict(self.item,family="demo")]},
                 "datasets/synthetic-v0/registry.json": self.reg}
        def write(path, val):
            encoded = json.dumps(val, ensure_ascii=False).encode()
            path.write_bytes(encoded)
            return sha256(encoded).hexdigest()
        self.ref = root / "refs.json"
        claim = {"id":"a:one","polarity":"positive","context":"ctx:abc",
                 "roles":{"subject":"c:x","relation":"r:x","object":"c:x"},
                 "sources":[{"id":"src:excerpt","description":self.item["text"]}]}
        self.raw = [{"id":"demo","assertions":[claim]}]
        lock = {"version":"ai-eng-v1","items":1,"ir":"0.2","family_partition":{"demo":"engineering-dev"},
                "public_files":{p:write(root/p,v) for p,v in paths.items()},
                "private_files":{"adjudicated.json":write(self.ref,self.raw)}}
        mf = root / "FROZEN.json"
        write(mf, lock)
        mock = patch.multiple(freeze, FREEZE=mf, ROOT=root)
        mock.start()
        self.addCleanup(mock.stop)

    def test_bound_inputs_and_citation_occurrences(self):
        report = score_frozen([self.item], self.reg, self.ref, self.raw)
        self.assertEqual(report["verified_source_occurrences"], 1)
        self.assertEqual((report["matched"], report["precision"], report["recall"]), (1,1,1))
        with self.assertRaisesRegex(ValueError,"盲包"):
            score_frozen([dict(self.item,text="其他")], self.reg, self.ref, self.raw)
        with self.assertRaisesRegex(ValueError,"登记表"):
            score_frozen([self.item],dict(self.reg,document_year=2030),self.ref,self.raw)
        with self.assertRaises(ValueError):
            score_frozen([self.item],self.reg,self.ref,[])

    def test_reject_reference_bytes_or_source_change(self):
        self.raw[0]["assertions"][0]["sources"][0]["description"] = "未经绑定的引文"
        with self.assertRaisesRegex(ValueError,"来源"):
            score_frozen([self.item], self.reg, self.ref, self.raw)
        self.ref.write_bytes(self.ref.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError,"摘要"):
            score_frozen([self.item], self.reg, self.ref, self.raw)
