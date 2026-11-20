from copy import deepcopy
import json
from pathlib import Path
import unittest

from ncsc import IRValidationError
from ncsc.rule_loader import load_rules


class RuleSetTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).parent / "contract/fixtures/rules-0.2/valid"
        self.rule = json.loads((folder / "r1-resource-unavailable.json").read_text(encoding="utf8"))
        self.declared = {"r:task:requires", "r:resource:unavailable", "r:status:blocked", "c:value:true"}

    def test_negative_dependency_is_checked_across_rules_in_either_order(self):
        other = deepcopy(self.rule)
        other["id"] = "other"
        other["premises"][0].update(relation="r:status:blocked", polarity="negative")
        other["conclusion"]["relation"] = "r:task:requires"
        for pair in ([self.rule, other], [other, self.rule]):
            with self.assertRaisesRegex(IRValidationError, "负向前提"):
                load_rules(pair, self.declared)
        other["status"] = "proposed"
        self.assertEqual(load_rules([self.rule, other], self.declared), [self.rule])

    def test_duplicate_active_id_and_undeclared_constant(self):
        with self.assertRaisesRegex(IRValidationError, "重复"):
            load_rules([self.rule, self.rule], self.declared)
        with self.assertRaisesRegex(IRValidationError, "未登记"):
            load_rules([self.rule], self.declared - {"c:value:true"})
