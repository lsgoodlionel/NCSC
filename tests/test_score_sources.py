import unittest

from baselines.evaluate import score


class SourceScoreTests(unittest.TestCase):
    def test_correct_proof_can_have_incomplete_sources(self):
        sources = [{"id": "s:one", "description": "合成甲"}, {"id": "s:two", "description": "合成乙"}]
        assertion = {"id": "a:one", "sources": sources, "polarity": "positive", "context": "ctx:test"}
        gold = {"derived_by": "r", "premises": ["a:one"]}
        item = {"id": "i", "assertions": [assertion], "queries": [{"id": "q",
                "query": {"context": "ctx:test", "valid_at": None},
                "expect": {"status": "支持", "evidence": [gold]}}]}
        for reported, expected in [(sources[::-1], 1), (sources[:1], 0), (None, 0),
                                   ([dict(sources[0], description="不符"), sources[1]], 0),
                                   (sources + sources[:1], 0)]:
            with self.subTest(sources=reported):
                leaf = {"assertion_id": "a:one"}
                if reported is not None:
                    leaf["sources"] = reported
                row = {"item_id": "i", "query_id": "q", "status": "支持",
                       "evidence": [dict(gold, sources=sources, trace=[leaf])]}
                report = score({"items": [item]}, [row])
                self.assertEqual(report["provenance_complete"]["matched"], 1)
                self.assertEqual(report["source_complete"], {"eligible": 1, "matched": expected, "rate": expected})
