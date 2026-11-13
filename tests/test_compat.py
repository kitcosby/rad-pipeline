"""Compatibility tests: the WP2 finding schema stays aligned with the seed.

The provided finding schema's field names are normative and must remain
stable, so the WP2 copy is byte-identical to the seed copy, and the
current finding fixture must validate against both.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jsonschema
from jsonschema import Draft202012Validator

from radpipe import validate

WP2_ROOT = Path(__file__).resolve().parents[1]
SEED_SCHEMA = (
    Path(__file__).resolve().parents[3] / "seed" / "schemas" / "finding.schema.json"
)
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "finding.json"


class FindingCompatibilityTests(unittest.TestCase):
    def test_wp2_finding_schema_byte_identical_to_seed(self):
        self.assertEqual(
            (WP2_ROOT / "schemas" / "finding.schema.json").read_bytes(),
            SEED_SCHEMA.read_bytes(),
        )

    def test_fixture_validates_against_seed_schema(self):
        with open(SEED_SCHEMA, encoding="utf-8") as fh:
            seed_schema = json.load(fh)
        with open(FIXTURE, encoding="utf-8") as fh:
            fixture = json.load(fh)
        errors = list(Draft202012Validator(seed_schema).iter_errors(fixture))
        self.assertEqual(errors, [])

    def test_fixture_validates_against_wp2_schema(self):
        with open(FIXTURE, encoding="utf-8") as fh:
            fixture = json.load(fh)
        self.assertEqual(validate.check(fixture, "finding"), [])


if __name__ == "__main__":
    unittest.main()
