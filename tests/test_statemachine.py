"""State machine tests (WP3): legal/illegal transitions and guards."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radpipe.evidence import EvidenceStore
from radpipe.statemachine import CycleMachine, IllegalTransitionError


def make_cycle(state="INTAKE"):
    return {
        "schema_version": "0.1",
        "project_id": "bibleapp",
        "cycle_id": "bibleapp-2026-11-12-001",
        "created_at": "2026-11-12T09:00:00Z",
        "intent": "State machine test cycle.",
        "baseline": {"status": "pending"},
        "state": state,
        "policy_profile": "nonprod-default",
        "artifact_inventory_ref": "inventory://bibleapp/test",
        "approval_refs": [],
        "open_findings": [],
    }


CHAIN = [
    "DESIGN_READY", "IMPLEMENTATION_READY", "BUILT", "BASELINED", "TESTED",
    "TRIAGED", "RECONCILING", "CORRECTED", "REGRESSION_VERIFIED",
    "ACCEPTANCE_READY",
]


class TestCycleMachine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(Path(self.tmp.name) / "evidence.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def machine(self, state="INTAKE"):
        return CycleMachine(self.store, make_cycle(state))

    def test_full_chain_and_release_authorization(self):
        m = self.machine()
        for target in CHAIN:
            m.transition(target)
            self.assertEqual(m.state, target)
        # RELEASED needs explicit recorded authorization.
        with self.assertRaises(IllegalTransitionError):
            m.transition("RELEASED")
        m.transition("RELEASED", authorization_ref="approval://kit/release-1")
        self.assertEqual(m.state, "RELEASED")
        self.assertTrue(self.store.verify().ok)
        self.assertEqual(len(self.store.records()), len(CHAIN) + 1)
        summaries = [r["summary"] for r in self.store.records()]
        self.assertIn("INTAKE -> DESIGN_READY", summaries[0])
        self.assertIn("ACCEPTANCE_READY -> RELEASED", summaries[-1])

    def test_illegal_jump_refused_and_records_nothing(self):
        m = self.machine()
        with self.assertRaises(IllegalTransitionError) as ctx:
            m.transition("BUILT")
        self.assertIn("INTAKE -> DESIGN_READY", str(ctx.exception))
        self.assertEqual(m.state, "INTAKE")
        self.assertEqual(self.store.records(), [])

    def test_unknown_and_same_state_refused(self):
        m = self.machine()
        with self.assertRaises(IllegalTransitionError):
            m.transition("SHIPPED")
        with self.assertRaises(IllegalTransitionError):
            m.transition("INTAKE")

    def test_side_state_requires_reason(self):
        m = self.machine()
        with self.assertRaises(IllegalTransitionError):
            m.transition("BLOCKED")
        m.transition("BLOCKED", reason="staging host unreachable")
        self.assertEqual(m.state, "BLOCKED")

    def test_blocked_returns_only_to_origin_with_verification(self):
        m = self.machine()
        m.transition("DESIGN_READY")
        m.transition("BLOCKED", reason="prerequisite missing")
        with self.assertRaises(IllegalTransitionError):
            m.transition("IMPLEMENTATION_READY")  # wrong return target
        with self.assertRaises(IllegalTransitionError):
            m.transition("DESIGN_READY")  # no verification recorded
        m.transition("DESIGN_READY", verification_ref="probe://staging/up")
        self.assertEqual(m.state, "DESIGN_READY")

    def test_waiting_for_input_requires_recorded_decision(self):
        m = self.machine()
        m.transition("WAITING_FOR_INPUT", reason="intent ambiguity")
        with self.assertRaises(IllegalTransitionError):
            m.transition("INTAKE")
        m.transition("INTAKE", decision_ref="decision://kit/2026-11-12/1")
        self.assertEqual(m.state, "INTAKE")

    def test_failed_retry_is_a_new_attempt(self):
        m = self.machine()
        m.transition("DESIGN_READY")
        m.transition("FAILED", reason="design review crashed")
        self.assertEqual(m.attempt, 1)
        m.transition("DESIGN_READY")
        self.assertEqual(m.attempt, 2)
        self.assertIn("attempt: 2", self.store.records()[-1]["summary"])
        self.assertTrue(self.store.verify().ok)

    def test_superseded_requires_successor_and_is_terminal(self):
        m = self.machine()
        with self.assertRaises(IllegalTransitionError):
            m.transition("SUPERSEDED")
        m.transition("SUPERSEDED", successor_cycle_id="bibleapp-2026-11-12-002")
        self.assertEqual(m.cycle["successor_cycle_id"], "bibleapp-2026-11-12-002")
        with self.assertRaises(IllegalTransitionError):
            m.transition("INTAKE")

    def test_cancelled_is_terminal(self):
        m = self.machine()
        m.transition("CANCELLED", reason="owner cancelled")
        with self.assertRaises(IllegalTransitionError):
            m.transition("BLOCKED", reason="again")


if __name__ == "__main__":
    unittest.main()
