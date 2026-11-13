"""Validation tests: fixtures pass; one test per rejection class."""

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from radpipe import validate

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name):
    with open(FIXTURES / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


class FixtureValidationTests(unittest.TestCase):
    def test_all_fixtures_validate(self):
        for kind in validate.KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(validate.check(load_fixture(kind), kind), [])

    def test_finding_embedded_link_validates_as_artifact_link(self):
        finding = load_fixture("finding")
        for link in finding["affected_artifacts"]:
            with self.subTest(artifact_id=link["artifact_id"]):
                # Embedded links carry no schema_version; the standalone
                # artifact-link schema must still accept them unchanged.
                self.assertNotIn("schema_version", link)
                self.assertEqual(validate.check(link, "artifact_link"), [])


class RejectionTests(unittest.TestCase):
    def assertRejected(self, record, kind, needle=None):
        errors = validate.check(record, kind)
        self.assertTrue(errors, f"expected rejection, got no errors: {errors}")
        if needle is not None:
            self.assertTrue(
                any(needle in e for e in errors),
                f"expected an error mentioning {needle!r}, got: {errors}",
            )
        with self.assertRaises(validate.ValidationError):
            validate.validate(record, kind)

    def test_missing_required_field(self):
        cycle = load_fixture("cycle")
        del cycle["intent"]
        self.assertRejected(cycle, "cycle", needle="intent")

    def test_wrong_type(self):
        stage = load_fixture("stage")
        stage["attempt"] = "1"  # string where an integer is required
        self.assertRejected(stage, "stage", needle="attempt")

    def test_unknown_enum_value_cycle_state(self):
        cycle = load_fixture("cycle")
        cycle["state"] = "SHIPPED"
        self.assertRejected(cycle, "cycle", needle="state")

    def test_unknown_enum_value_evidence_class(self):
        evidence = load_fixture("evidence")
        evidence["class"] = "GUESSED"
        self.assertRejected(evidence, "evidence", needle="class")

    def test_unknown_schema_version(self):
        finding = load_fixture("finding")
        finding["schema_version"] = "9.9"
        self.assertRejected(finding, "finding", needle="schema_version")

    def test_additional_property_rejected(self):
        finding = load_fixture("finding")
        finding["surprise_field"] = "not in the contract"
        self.assertRejected(finding, "finding", needle="surprise_field")

    def test_pattern_violation_finding_id(self):
        finding = load_fixture("finding")
        finding["finding_id"] = "BUG-123"
        self.assertRejected(finding, "finding", needle="finding_id")

    def test_bad_datetime(self):
        cycle = load_fixture("cycle")
        cycle["created_at"] = "12 Nov 2026, morning"
        self.assertRejected(cycle, "cycle", needle="created_at")

    def test_impossible_datetime(self):
        approval = load_fixture("approval")
        approval["decided_at"] = "2026-13-40T25:61:61Z"
        self.assertRejected(approval, "approval", needle="decided_at")

    def test_bad_sha256(self):
        evidence = load_fixture("evidence")
        evidence["sha256"] = "deadbeef"
        self.assertRejected(evidence, "evidence", needle="sha256")

    def test_below_minimum_attempt(self):
        stage = load_fixture("stage")
        stage["attempt"] = 0
        self.assertRejected(stage, "stage", needle="attempt")

    def test_empty_classifications(self):
        finding = load_fixture("finding")
        finding["classifications"] = []
        self.assertRejected(finding, "finding", needle="classifications")

    def test_duplicate_classifications(self):
        finding = load_fixture("finding")
        finding["classifications"] = ["implementation", "implementation"]
        self.assertRejected(finding, "finding", needle="classifications")

    def test_superseded_cycle_requires_successor(self):
        cycle = load_fixture("cycle")
        cycle["state"] = "SUPERSEDED"
        self.assertRejected(cycle, "cycle", needle="successor_cycle_id")
        cycle["successor_cycle_id"] = "bibleapp-2026-11-13-001"
        self.assertEqual(validate.check(cycle, "cycle"), [])

    def test_recorded_baseline_requires_identity(self):
        cycle = load_fixture("cycle")
        cycle["baseline"] = {"status": "recorded"}
        self.assertRejected(cycle, "cycle")
        cycle["baseline"] = {"status": "recorded", "commit": "abc123"}
        self.assertEqual(validate.check(cycle, "cycle"), [])

    def test_stage_command_ref_and_exit_code_paired(self):
        stage = load_fixture("stage")
        del stage["exit_code"]
        self.assertRejected(stage, "stage", needle="exit_code")
        stage2 = load_fixture("stage")
        del stage2["command_ref"]
        self.assertRejected(stage2, "stage", needle="command_ref")

    def test_stage_completed_before_started(self):
        stage = load_fixture("stage")
        stage["completed_at"] = "2026-11-12T08:00:00Z"  # before started_at
        self.assertRejected(stage, "stage", needle="completed_at")

    def test_errors_are_specific(self):
        cycle = load_fixture("cycle")
        del cycle["intent"]
        cycle["state"] = "NOPE"
        errors = validate.check(cycle, "cycle")
        self.assertGreaterEqual(len(errors), 2)
        self.assertTrue(all(e.startswith("$") for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
