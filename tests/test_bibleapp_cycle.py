"""WP4 adapter cycle tests: the full baseline cycle over fixtures,
QA battery results recorded with exact exit codes, the artifact
inventory with content hashes, the CEG generation gate denied by
default and permitted only when the cleanup flag is DONE, and the
baseline report tracing every value to the evidence store."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapter_fixture as fx

from radpipe.adapters.bibleapp import BibleAppAdapter
from radpipe.evidence import EvidenceStore, content_hash

PY = fx.PY
HELPERS = fx.HELPERS


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FullCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fx = fx.make_repo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_cycle_completes_with_exact_report(self):
        config = fx.make_config(
            self.root, self.fx["repo"],
            batteries=[{"name": "smoke",
                        "argv": [PY, str(HELPERS / "battery_ok.py"), "smoke"]}],
        )
        adapter = BibleAppAdapter(config, base_dir=self.root)
        run = adapter.run_cycle(cycle_id="bibleapp-cycle-001",
                                run_id="run-bibleapp-cycle-001")
        self.assertEqual(run.run_result.status, "completed")
        self.assertEqual(run.run_result.next_cycle_id, "bibleapp-cycle-002")

        report = run.report
        self.assertEqual(report["run_status"], "completed")
        qa = report["qa"]
        self.assertEqual(len(qa), 1)
        self.assertEqual(qa[0]["status"], "succeeded")
        self.assertEqual(qa[0]["attempts"], 1)
        self.assertEqual(qa[0]["exit_codes"], [0])
        self.assertTrue(qa[0]["evidence_ids"])

        inventory = report["inventory"]
        self.assertEqual(inventory["count"], 5)
        by_location = {a["canonical_location"]: a for a in inventory["artifacts"]}
        self.assertEqual(by_location["README.md"]["type"], "readme")
        self.assertEqual(
            by_location["DESCRIPTION"]["type"], "repository_description"
        )
        self.assertEqual(
            by_location["package.json"]["type"], "package_description"
        )
        self.assertEqual(by_location["docs/guide.md"]["type"], "architecture")
        self.assertEqual(by_location["suites/sample.ceg"]["type"], "ceg")
        for location, artifact in by_location.items():
            self.assertEqual(
                artifact["content_hash"], sha256_of(self.fx["repo"] / location)
            )
        self.assertTrue(report["evidence"]["chain_ok"])
        self.assertIn("# BibleApp baseline report", run.report_markdown)
        self.assertIn(self.fx["commit"], run.report_markdown)

    def test_report_values_trace_to_evidence_store(self):
        config = fx.make_config(self.root, self.fx["repo"])
        adapter = BibleAppAdapter(config, base_dir=self.root)
        run = adapter.run_cycle(cycle_id="bibleapp-trace-001",
                                run_id="run-bibleapp-trace-001")
        report = run.report
        store = EvidenceStore(config["evidence_path"])
        records = store.records()
        self.assertEqual(report["evidence"]["records"], len(records))
        self.assertTrue(report["evidence"]["chain_ok"])

        inventory_payload = json.loads(
            (adapter.work_dir / "inventory.json").read_text(encoding="utf-8")
        )
        inventory_hash = content_hash(
            {"artifacts": inventory_payload["artifacts"]}
        )
        inventory_records = [
            r for r in records if r.get("sha256") == inventory_hash
        ]
        self.assertEqual(len(inventory_records), 1)
        self.assertEqual(
            inventory_records[0]["evidence_id"], report["inventory"]["evidence_id"]
        )
        self.assertEqual(
            inventory_records[0]["related_artifact_ids"],
            [a["artifact_id"] for a in report["inventory"]["artifacts"]],
        )

    def test_failing_battery_exit_code_recorded(self):
        config = fx.make_config(
            self.root, self.fx["repo"],
            batteries=[
                {"name": "smoke",
                 "argv": [PY, str(HELPERS / "battery_ok.py"), "smoke"]},
                {"name": "regression",
                 "argv": [PY, str(HELPERS / "battery_fail.py"), "regression"]},
            ],
        )
        adapter = BibleAppAdapter(config, base_dir=self.root)
        run = adapter.run_cycle(cycle_id="bibleapp-qa-001",
                                run_id="run-bibleapp-qa-001")
        self.assertEqual(run.run_result.status, "failed")
        qa = {entry["task_id"]: entry for entry in run.report["qa"]}
        self.assertEqual(len(qa), 2)
        self.assertEqual(qa["qa-0-smoke"]["exit_codes"], [0])
        self.assertEqual(qa["qa-0-smoke"]["status"], "succeeded")
        self.assertEqual(qa["qa-1-regression"]["exit_codes"], [3])
        self.assertEqual(qa["qa-1-regression"]["status"], "failed")
        self.assertEqual(qa["qa-1-regression"]["attempts"], 1)


class CegGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fx = fx.make_repo(self.root)
        self.marker = self.root / "generated-marker.txt"

    def tearDown(self):
        self.tmp.cleanup()

    def _config(self, **overrides):
        base = {
            "ceg_generation": {
                "requested": True,
                "argv": [PY, str(HELPERS / "fake_ceg.py"), str(self.marker)],
            },
        }
        base.update(overrides)
        return fx.make_config(self.root, self.fx["repo"], **base)

    def test_generation_denied_by_default_and_evidenced(self):
        # No ceg_paradigm_cleanup key at all: the default is not DONE.
        config = self._config()
        self.assertNotIn("ceg_paradigm_cleanup", config)
        adapter = BibleAppAdapter(config, base_dir=self.root)
        run = adapter.run_cycle(cycle_id="bibleapp-ceg-001",
                                run_id="run-bibleapp-ceg-001")
        self.assertEqual(run.run_result.status, "blocked")
        self.assertFalse(self.marker.exists())
        generation = run.report["ceg_generation"]
        self.assertTrue(generation["requested"])
        self.assertFalse(generation["gate"]["allowed"])
        self.assertIn("CEG-PARADIGM-CLEANUP", generation["gate"]["reason"])
        store = EvidenceStore(config["evidence_path"])
        denials = [
            r for r in store.records()
            # stage/cycle records share the store but carry no summary
            if "DENIED" in r.get("summary", "")
            and "ceg-generation" in r.get("summary", "")
        ]
        self.assertEqual(len(denials), 1)

    def test_generation_denied_when_cleanup_in_progress(self):
        config = self._config(ceg_paradigm_cleanup="IN_PROGRESS")
        adapter = BibleAppAdapter(config, base_dir=self.root)
        run = adapter.run_cycle(cycle_id="bibleapp-ceg-002",
                                run_id="run-bibleapp-ceg-002")
        self.assertEqual(run.run_result.status, "blocked")
        self.assertFalse(self.marker.exists())

    def test_generation_permitted_when_cleanup_done(self):
        config = self._config(ceg_paradigm_cleanup="DONE")
        adapter = BibleAppAdapter(config, base_dir=self.root)
        run = adapter.run_cycle(cycle_id="bibleapp-ceg-003",
                                run_id="run-bibleapp-ceg-003")
        self.assertEqual(run.run_result.status, "completed")
        self.assertTrue(self.marker.exists())
        self.assertIn("fake generation ran",
                      self.marker.read_text(encoding="utf-8"))
        generation = run.report["ceg_generation"]
        self.assertTrue(generation["gate"]["allowed"])
        self.assertEqual(generation["task_status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
