import json
import tempfile
import unittest
from pathlib import Path

from annotation.round_manifest import create, verify
from annotation.trial import prepare


class RoundManifestTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / "round"
        prepare(self.folder)
        self.docs = Path(temp.name)
        (self.docs / "GUIDE.md").write_bytes(b"guide\r\n")
        (self.docs / "TRIAL_PROTOCOL.md").write_bytes(b"protocol\n")

    def test_prepare_verify_and_do_not_overwrite(self):
        result = create(self.folder, self.docs)
        self.assertEqual(verify(self.folder, self.docs), result)
        self.assertEqual((result["dataset"], result["ir_version"], result["freeze_status"]),
                         ("synthetic-v0", "0.2", "pending"))
        self.assertEqual(result["item_ids"], [r["id"] for r in
                         json.loads((self.folder / "packet.json").read_text(encoding="utf-8"))])
        target = self.folder / "round.json"
        target.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            create(self.folder, self.docs)
        self.assertEqual(target.read_bytes(), b"existing")

    def test_each_input_is_verified_by_exact_bytes(self):
        create(self.folder, self.docs)
        for folder, name in ((self.docs, "GUIDE.md"), (self.docs, "TRIAL_PROTOCOL.md"),
                             (self.folder, "packet.json"), (self.folder, "registry.json")):
            with self.subTest(name=name):
                path = folder / name
                old = path.read_bytes()
                path.write_bytes(old + b"\n")
                with self.assertRaisesRegex(ValueError, name):
                    verify(self.folder, self.docs)
                path.write_bytes(old)

    def test_rejects_unblinded_packet_and_tampered_status(self):
        create(self.folder, self.docs)
        target = self.folder / "round.json"
        manifest = json.loads(target.read_text(encoding="utf-8"))
        manifest["freeze_status"] = "frozen"
        target.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "轮次字段"):
            verify(self.folder, self.docs)
        (self.folder / "packet.json").write_text('[{"id":"one","text":"t","gold":[]}]', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "只接受"):
            verify(self.folder, self.docs)
