"""Evidence store tests: chaining, append-only behavior, tamper detection."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from radpipe import validate
from radpipe.evidence import GENESIS_HASH, EvidenceStore, verify_file

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAKE_GITHUB_TOKEN = "ghp_" + "B" * 36


def load_evidence_fixture():
    with open(FIXTURES / "evidence.json", encoding="utf-8") as fh:
        return json.load(fh)


def make_record(n):
    record = load_evidence_fixture()
    record["evidence_id"] = f"EVD-20261112-{n:04d}"
    record["summary"] = f"Synthetic evidence record {n}."
    return record


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "evidence.jsonl"
        self.store = EvidenceStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()


class AppendAndVerifyTests(StoreTestCase):
    def test_chain_verifies(self):
        for n in range(1, 4):
            self.store.append(make_record(n))
        report = self.store.verify()
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.count, 3)

    def test_chain_linkage_and_sequence(self):
        envelopes = [self.store.append(make_record(n)) for n in range(1, 4)]
        self.assertEqual([e["seq"] for e in envelopes], [0, 1, 2])
        self.assertEqual(envelopes[0]["prev_hash"], GENESIS_HASH)
        self.assertEqual(envelopes[1]["prev_hash"], envelopes[0]["hash"])
        self.assertEqual(envelopes[2]["prev_hash"], envelopes[1]["hash"])
        self.assertTrue(all(len(e["hash"]) == 64 for e in envelopes))

    def test_records_round_trip_in_order(self):
        for n in range(1, 4):
            self.store.append(make_record(n))
        records = self.store.records()
        self.assertEqual(
            [r["evidence_id"] for r in records],
            ["EVD-20261112-0001", "EVD-20261112-0002", "EVD-20261112-0003"],
        )

    def test_append_only_prior_bytes_unchanged(self):
        self.store.append(make_record(1))
        before = self.path.read_bytes()
        self.store.append(make_record(2))
        after = self.path.read_bytes()
        self.assertTrue(after.startswith(before))
        self.assertGreater(len(after), len(before))

    def test_verify_empty_store_is_ok(self):
        report = verify_file(self.path)
        self.assertTrue(report.ok)
        self.assertEqual(report.count, 0)

    def test_invalid_record_refused_and_not_persisted(self):
        bad = make_record(1)
        del bad["summary"]
        with self.assertRaises(validate.ValidationError):
            self.store.append(bad)
        self.assertFalse(self.path.exists())


class TamperDetectionTests(StoreTestCase):
    def _write_three(self):
        for n in range(1, 4):
            self.store.append(make_record(n))
        return self.path.read_text(encoding="utf-8").splitlines(keepends=True)

    def test_edited_record_detected(self):
        lines = self._write_three()
        envelope = json.loads(lines[1])
        envelope["record"]["summary"] = "Forged summary."
        lines[1] = json.dumps(envelope) + "\n"
        self.path.write_text("".join(lines), encoding="utf-8")
        report = verify_file(self.path)
        self.assertFalse(report.ok)
        self.assertTrue(any("hash mismatch" in e for e in report.errors), report.errors)

    def test_deleted_record_detected(self):
        lines = self._write_three()
        del lines[1]
        self.path.write_text("".join(lines), encoding="utf-8")
        report = verify_file(self.path)
        self.assertFalse(report.ok)

    def test_reordered_records_detected(self):
        lines = self._write_three()
        lines[1], lines[2] = lines[2], lines[1]
        self.path.write_text("".join(lines), encoding="utf-8")
        report = verify_file(self.path)
        self.assertFalse(report.ok)

    def test_append_refuses_to_extend_tampered_chain(self):
        lines = self._write_three()
        envelope = json.loads(lines[2])
        envelope["record"]["actor"] = "mallory"
        lines[2] = json.dumps(envelope) + "\n"
        self.path.write_text("".join(lines), encoding="utf-8")
        with self.assertRaises(Exception):
            self.store.append(make_record(4))


class RedactionOnWriteTests(StoreTestCase):
    def test_planted_token_never_reaches_disk(self):
        record = make_record(1)
        record["summary"] = f"Probe ran with {FAKE_GITHUB_TOKEN} in the header."
        self.store.append(record)
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn(FAKE_GITHUB_TOKEN, raw)
        stored = self.store.records()[0]
        self.assertIn("***REDACTED***", stored["summary"])
        self.assertTrue(self.store.verify().ok)


if __name__ == "__main__":
    unittest.main()
