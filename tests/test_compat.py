"""Compatibility tests: the WP2 finding schema stays aligned with the seed.

The provided finding schema's field names are normative and must remain
stable, so the WP2 copy is byte-identical to the seed copy, and the
current finding fixture must validate against it.

Byte-identity is checked against the seed schema's pinned SHA-256 so the
test is self-contained on any machine (an earlier version resolved the
seed tree by relative path and errored wherever that layout was absent;
caught by the laptop cross-run, jobs 19896/19904, 2026-11-12).
"""

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonschema import Draft202012Validator

from radpipe import validate

WP2_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = WP2_ROOT / "schemas" / "finding.schema.json"
# SHA-256 of the seeded schemas/finding.schema.json (kitcosby/rad-pipeline,
# seed commit e2357878). Update this pin only in the same commit that
# deliberately changes the seed schema.
SEED_SCHEMA_SHA256 = (
    "ef814b3e39318f6d8fd27f576290bc02880b592aa08039cbe8f0d8227dac09fa"
)
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "finding.json"


class FindingCompatibilityTests(unittest.TestCase):
    def test_wp2_finding_schema_byte_identical_to_seed(self):
        digest = hashlib.sha256(SCHEMA_FILE.read_bytes()).hexdigest()
        self.assertEqual(digest, SEED_SCHEMA_SHA256)

    def test_fixture_validates_against_seed_schema(self):
        with open(SCHEMA_FILE, encoding="utf-8") as fh:
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
