import copy
import tempfile
import unittest
from pathlib import Path

from annotation.trial import DATA, polarity_agreement, prepare, read, validate_sheet


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.registry = read(DATA / "registry.json")
        items = read(DATA / "items.json")["items"][:2]
        self.packet = [{"id": item["id"], "text": item["text"]} for item in items]
        self.a = [{"id": i["id"], "assertions": i["assertions"], "not_annotated": []} for i in items]
        self.b = copy.deepcopy(self.a)

    def agreement(self):
        return polarity_agreement(self.packet, self.registry, self.a, self.b)

    def test_blind_packet_and_unfinished_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "trial"
            prepare(folder)
            packet = read(folder / "packet.json")
            self.assertTrue(all(set(item) == {"id", "text"} for item in packet))
            a, b = [read(folder / f"annotator-{who}.json") for who in ("a", "b")]
            pending = validate_sheet(packet, self.registry, a)
            self.assertEqual(pending, [i["id"] for i in packet])
            with self.assertRaisesRegex(ValueError, "不能计算"):
                polarity_agreement(packet, self.registry, a, b)
            with self.assertRaises(FileExistsError):
                prepare(folder)

    def test_agreement_reordering_and_source_identity(self):
        self.b.reverse()
        self.b[0]["assertions"][0]["id"] = "a:other-id"
        self.b[0]["assertions"][0]["sources"] = [self.registry["sources"][-1]]
        report = self.agreement()
        self.assertEqual(report["kappa"], 1)
        self.assertEqual(report["single_label_pairs"], 2)
        self.assertEqual(report["confusion_a_by_b"]["negative"]["negative"], 1)
        for row in self.b:
            claim = row["assertions"][0]
            claim["polarity"] = "positive" if claim["polarity"] == "negative" else "negative"
        self.assertEqual(self.agreement()["kappa"], -1)

    def test_no_pairs_changed_partition_and_undefined_constant(self):
        self.b[0]["assertions"][0].pop("valid_at")
        r = self.agreement()
        self.assertEqual((r["single_label_pairs"], r["a_only_keys"], r["b_only_keys"]), (1, 1, 1))
        self.assertIsNone(r["kappa"])
        self.assertEqual(r["reason"], "constant_marginals")
        self.b[1]["assertions"] = []
        self.assertEqual(self.agreement()["reason"], "no_shared_pairs")

    def test_conflicting_sources_do_not_silently_change_the_cohort(self):
        neg = copy.deepcopy(self.a[0]["assertions"][0])
        neg.update(id="a:counter", polarity="negative")
        self.a[0]["assertions"].append(neg)
        r = self.agreement()
        self.assertEqual((r["shared_keys"], r["multi_label_keys"]), (2, 1))
        self.assertIsNone(r["kappa"])
        self.assertEqual(r["reason"], "multi_label_policy_required")

    def test_incomplete_malformed_and_duplicate_sheets(self):
        malformed = copy.deepcopy(self.b)
        malformed[0]["not_annotated"] = None
        bad_span = copy.deepcopy(self.b)
        bad_span[0]["not_annotated"] = [{"span": "absent text", "reason": "absence"}]
        bad_context = copy.deepcopy(self.b)
        bad_context[0]["assertions"][0]["context"] = "ctx:missing"
        for sheet in (self.b[:-1], self.b * 2, malformed, bad_span, bad_context):
            with self.subTest(sheet=sheet), self.assertRaises(ValueError):
                validate_sheet(self.packet, self.registry, sheet)
