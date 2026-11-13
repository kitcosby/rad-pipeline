"""WP4 git baseline tests: a temp git repo fixture, with the expected
branch/commit/tags/dirty state computed by an independent oracle
(direct subprocess git) — never through the adapter under test."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapter_fixture as fx

from radpipe.adapters import probe
from radpipe.adapters.bibleapp import BibleAppAdapter
from radpipe.evidence import EvidenceStore, content_hash


class GitProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fx = fx.make_repo(self.root)
        self.repo = self.fx["repo"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_probe_captures_exact_identity(self):
        result = probe.git_baseline(str(self.repo))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["branch"], "main")
        self.assertEqual(result["branch"], self.fx["branch"])
        self.assertEqual(result["commit"], self.fx["commit"])
        self.assertEqual(result["tags"], ["v0.1.0"])
        self.assertEqual(result["tags"], self.fx["tags"])
        self.assertEqual(result["tag_count"], 1)
        self.assertTrue(result["is_clean"])
        self.assertEqual(result["dirty_count"], 0)
        self.assertEqual(result["dirty_entries"], [])

    def test_probe_captures_dirty_state_exactly(self):
        (self.repo / "README.md").write_text("# Changed\n")
        (self.repo / "notes.txt").write_text("untracked\n")
        result = probe.git_baseline(str(self.repo))
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["is_clean"])
        oracle = [
            line for line in fx.git(self.repo, "status", "--porcelain").splitlines()
            if line.strip()
        ]
        self.assertEqual(result["dirty_entries"], oracle)
        self.assertEqual(result["dirty_count"], 2)
        self.assertEqual(
            sorted(result["dirty_entries"]), [" M README.md", "?? notes.txt"]
        )

    def test_probe_on_non_repo_fails_closed(self):
        result = probe.git_baseline(str(self.root / "projectless"))
        self.assertFalse(result["ok"])
        self.assertIn("error", result)


class GitAdapterCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fx = fx.make_repo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_adapter_report_matches_oracle_and_evidence(self):
        config = fx.make_config(self.root, self.fx["repo"])
        adapter = BibleAppAdapter(config, base_dir=self.root)
        run = adapter.run_cycle(cycle_id="bibleapp-test-001",
                                run_id="run-bibleapp-test-001")
        report = run.report
        git = report["git"]
        self.assertEqual(git["branch"], self.fx["branch"])
        self.assertEqual(git["commit"], self.fx["commit"])
        self.assertEqual(git["tags"], self.fx["tags"])
        self.assertEqual(git["tag_count"], len(self.fx["tags"]))
        self.assertTrue(git["is_clean"])
        self.assertEqual(report["baseline"], {
            "status": "recorded",
            "repository": str(self.fx["repo"]),
            "branch": self.fx["branch"],
            "commit": self.fx["commit"],
        })
        # The report's git values trace to an evidence record whose
        # hash is the content hash of the exact probe result file.
        store = EvidenceStore(config["evidence_path"])
        self.assertTrue(store.verify().ok)
        probe_payload = adapter.work_dir.joinpath("git-baseline.json")
        import json as _json
        probe_dict = _json.loads(probe_payload.read_text(encoding="utf-8"))
        matches = [
            r for r in store.records()
            if r.get("sha256") == content_hash(probe_dict)
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["evidence_id"], git["evidence_id"])
        self.assertIn(self.fx["commit"], matches[0]["summary"])
        self.assertIn(self.fx["branch"], matches[0]["summary"])


if __name__ == "__main__":
    unittest.main()
