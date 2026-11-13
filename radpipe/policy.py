"""Policy gate interface (WP3).

Before a stage runs, the scheduler consults the gates the stage names.
A gate returns a GateDecision; the registry evaluates every named gate
and the stage runs only if all allow. Fail-closed throughout
(CONTRACTS.md: "Unknown policy result is a deny"):

- a gate name that is not registered is a denial;
- a gate that raises is a denial (the exception is its reason);
- a gate returning anything but an explicit allow is a denial.

The standing CEG rule (ARCHITECTURE.md section 9, IMPLEMENTATION-PLAN
WP4): no CEG generation or suite regeneration until CEG-PARADIGM-CLEANUP
is DONE. ``CegGenerationGate`` models it: a stage whose action is
``ceg_generation`` is denied unless the evaluation context's flags carry
``ceg_paradigm_cleanup == "DONE"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class GateDecision:
    gate: str
    allowed: bool
    reason: str

    @classmethod
    def allow(cls, gate: str, reason: str = "gate satisfied") -> "GateDecision":
        return cls(gate=gate, allowed=True, reason=reason)

    @classmethod
    def deny(cls, gate: str, reason: str) -> "GateDecision":
        return cls(gate=gate, allowed=False, reason=reason)


class PolicyGate(Protocol):
    """A named, consultable check. ``name`` is how stages refer to it."""

    name: str

    def evaluate(self, context: dict[str, Any]) -> GateDecision:
        ...


@dataclass
class GateRegistry:
    """Holds the gates a run may consult, by name."""

    gates: dict[str, PolicyGate] = field(default_factory=dict)

    def register(self, gate: PolicyGate) -> "GateRegistry":
        self.gates[gate.name] = gate
        return self

    def evaluate(self, gate_name: str, context: dict[str, Any]) -> GateDecision:
        gate = self.gates.get(gate_name)
        if gate is None:
            return GateDecision.deny(
                gate_name,
                f"unknown policy gate {gate_name!r}: not registered (deny by default)",
            )
        try:
            decision = gate.evaluate(context)
        except Exception as exc:  # a crashing gate is a deny, never a pass
            return GateDecision.deny(
                gate_name, f"gate {gate_name!r} raised {type(exc).__name__}: {exc}"
            )
        if not isinstance(decision, GateDecision) or decision.gate != gate_name:
            return GateDecision.deny(
                gate_name, f"gate {gate_name!r} returned a malformed decision (deny)"
            )
        return decision

    def evaluate_all(
        self, gate_names: list[str], context: dict[str, Any]
    ) -> list[GateDecision]:
        return [self.evaluate(name, context) for name in gate_names]


class FlagGate:
    """Allows iff ``context['flags'][flag] == expected``.

    The generic precondition gate: a named precondition flag must hold
    an exact value (e.g. "DONE") before the stage may run.
    """

    def __init__(self, name: str, flag: str, expected: Any = True):
        self.name = name
        self.flag = flag
        self.expected = expected

    def evaluate(self, context: dict[str, Any]) -> GateDecision:
        actual = (context.get("flags") or {}).get(self.flag)
        if actual == self.expected:
            return GateDecision.allow(
                self.name, f"flag {self.flag!r} is {self.expected!r}"
            )
        return GateDecision.deny(
            self.name,
            f"precondition flag {self.flag!r} is {actual!r}, requires {self.expected!r}",
        )


class CegGenerationGate:
    """The standing CEG gate: CEG generation is blocked until the
    paradigm-cleanup gate is DONE (context flag ``ceg_paradigm_cleanup``).
    """

    name = "ceg-generation"
    FLAG = "ceg_paradigm_cleanup"

    def evaluate(self, context: dict[str, Any]) -> GateDecision:
        actual = (context.get("flags") or {}).get(self.FLAG)
        if actual == "DONE":
            return GateDecision.allow(
                self.name, "CEG paradigm cleanup is DONE; generation permitted"
            )
        return GateDecision.deny(
            self.name,
            "CEG generation is blocked until CEG-PARADIGM-CLEANUP is DONE "
            f"(flag {self.FLAG!r} is {actual!r})",
        )
