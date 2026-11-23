import unittest

from annotation.ten_classes import summarize


def row(i, a, b, ak="entity", bk="event"):
    return {"id": str(i), "a": {"tags": a, "kind": ak}, "b": {"tags": b, "kind": bk}}


def report(*rows):
    return summarize({"tags_group": "T", "concepts": list(rows)})


class H1Tests(unittest.TestCase):
    def test_shared_subset_and_full_batch(self):
        rows = [row(1, [1], [2]), row(2, [2], [1], "event", "entity"),
                row(3, [1], [1], bk=None), row(4, [], []),
                row(5, None, [1], ak=None), row(6, [1, 2], [2, 3]), row(7, [], [1])]
        result = report(*rows)
        self.assertEqual(result, report(*reversed(rows)))
        p = result["paired"]
        self.assertEqual((p["n"], p["ids"]), (2, ["1", "2"]))
        self.assertEqual(p["ten_class_kappa"]["value"], -1)
        self.assertEqual(p["kind_kappa"]["value"], -1)
        self.assertEqual(p["ten_class_kappa"]["a_counts"][1], 1)
        self.assertEqual(p["kind_kappa"]["b_counts"]["event"], 1)
        self.assertTrue(p["kappas_comparable"])
        self.assertEqual(p["exclusions_overlapping"]["a.kind.missing"], 1)
        self.assertEqual(p["exclusions_overlapping"]["a.tags.missing"], 1)
        self.assertEqual(result["raters"]["a"]["valid_n"], 6)
        self.assertEqual(result["raters"]["a"]["unclassifiable_rate"], 2 / 6)
        j = result["jaccard"]
        self.assertEqual((j["valid_n"], j["both_empty"], j["missing_pairs"]), (5, 1, 1))
        self.assertAlmostEqual(j["mean"], (1 + 1 / 3) / 5)

    def test_constant_or_empty_cases(self):
        p = report(row(1, [0], [0]), row(2, [0], [0], "event", "entity"))["paired"]
        self.assertEqual(p["ten_class_kappa"]["na_reason"], "constant_marginals")
        self.assertEqual(p["kind_kappa"]["value"], -1)
        self.assertFalse(p["kappas_comparable"])
        r = report(row(1, None, []))
        self.assertIsNone(r["raters"]["a"]["single_rate"])
        self.assertEqual(r["raters"]["b"]["unclassifiable_rate"], 1)
        self.assertEqual(r["jaccard"]["na_reason"], "no_nonempty_paired_union")
        self.assertEqual(r["paired"]["kind_kappa"]["na_reason"], "no_paired_concepts")

    def test_invalid_records(self):
        for tags in ([1, 1], [True], [10], ["1"], "1"):
            with self.subTest(tags=tags), self.assertRaises(ValueError):
                report(row(1, tags, []))
        with self.assertRaises(ValueError):
            report(row(1, [1], [2], ak="unknown"))
        with self.assertRaises(ValueError):
            report(row(1, [], []), row(1, [], []))
