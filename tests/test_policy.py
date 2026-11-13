"""Policy gate tests (WP3): fail-closed registry and the CEG gate."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radpipe.policy import (
    CegGenerationGate,
    FlagGate,
    GateDecision,
    GateRegistry,
)


def ctx(flags=None):
    return {"flags": flags or {}, "action": "ceg_generation", "stage_id": "gen"}


class TestGates(unittest.TestCase):
    def test_flag_gate(self):
        gate = FlagGate("needs-done", "cleanup", expected="DONE")
        self.assertTrue(gate.evaluate(ctx({"cleanup": "DONE"})).allowed)
        self.assertFalse(gate.evaluate(ctx({"cleanup": "STARTED"})).allowed)
        self.assertFalse(gate.evaluate(ctx()).allowed)

    def test_ceg_gate_blocks_until_cleanup_done(self):
        gate = CegGenerationGate()
        self.assertFalse(gate.evaluate(ctx()).allowed)
        self.assertFalse(gate.evaluate(ctx({"ceg_paradigm_cleanup": "STARTED"})).allowed)
        decision = gate.evaluate(ctx({"ceg_paradigm_cleanup": "DONE"}))
        self.assertTrue(decision.allowed)

    def test_registry_unknown_gate_denies(self):
        registry = GateRegistry()
        decision = registry.evaluate("not-a-gate", ctx())
        self.assertFalse(decision.allowed)
        self.assertIn("not registered", decision.reason)

    def test_registry_raising_gate_denies(self):
        class Boom:
            name = "boom"

            def evaluate(self, context):
                raise RuntimeError("kaboom")

        decision = GateRegistry().register(Boom()).evaluate("boom", ctx())
        self.assertFalse(decision.allowed)
        self.assertIn("kaboom", decision.reason)

    def test_registry_malformed_decision_denies(self):
        class Wrong:
            name = "mine"

            def evaluate(self, context):
                return GateDecision.allow("someone-elses-gate")

        decision = GateRegistry().register(Wrong()).evaluate("mine", ctx())
        self.assertFalse(decision.allowed)

    def test_evaluate_all(self):
        registry = GateRegistry()
        registry.register(CegGenerationGate())
        registry.register(FlagGate("f", "x", expected=1))
        decisions = registry.evaluate_all(
            ["ceg-generation", "f"], ctx({"ceg_paradigm_cleanup": "DONE", "x": 1})
        )
        self.assertEqual([d.allowed for d in decisions], [True, True])


if __name__ == "__main__":
    unittest.main()
