import json
import unittest
from pathlib import Path

from ncsc.core import IRValidationError, validate_document


class SingleLineTests(unittest.TestCase):
    def test_alias_and_source_use_same_line_boundaries(self):
        path = Path(__file__).parent / "contract/fixtures/0.2/valid/example-migrated.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        for container, key in [(doc["concepts"][0]["aliases"], 0),
                               (doc["assertions"][0]["sources"][0], "description")]:
            for boundary in "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029":
                with self.subTest(key=key, boundary=repr(boundary)):
                    container[key] = "甲" + boundary + "乙"
                    with self.assertRaises(IRValidationError):
                        validate_document(doc)
            container[key] = "甲\t乙"
            validate_document(doc)
