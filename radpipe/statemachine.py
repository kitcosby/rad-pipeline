"""Cycle state machine (WP3) — STATE-MACHINE.md as executable guards.

The primary lifecycle is a linear chain:

    INTAKE -> DESIGN_READY -> IMPLEMENTATION_READY -> BUILT -> BASELINED
    -> TESTED -> TRIAGED -> RECONCILING -> CORRECTED
    -> REGRESSION_VERIFIED -> ACCEPTANCE_READY -> RELEASED

Side states (STATE-MACHINE.md "Side-state rules"):

- Any non-terminal state may move to WAITING_FOR_INPUT, BLOCKED, FAILED
  or CANCELLED, with a reason.
- WAITING_FOR_INPUT returns only to the state it was entered from, and
  only when the referenced decision is recorded (``decision_ref``).
- BLOCKED returns only to the state it was entered from, and only when
  the prerequisite is independently verified (``verification_ref``).
- FAILED returns only to the state it was entered from, as a new
  attempt; the machine's attempt counter increments and prior evidence
  remains immutable.
- SUPERSEDED may be entered from any non-terminal state and requires a
  successor cycle reference (``successor_cycle_id``).
- RELEASED is reachable only from ACCEPTANCE_READY and requires an
  explicit recorded authorization (``authorization_ref``).
- RELEASED, CANCELLED and SUPERSEDED are terminal.

PROVISIONAL choices where the spec is silent (see README-WP3.md):
the "returns only" rules are read as "returns to the state the side
state was entered from" (the last primary-lifecycle state); entering a
side state from another side state does not change that return target.

Every accepted transition is recorded as an evidence record in the
WP2 EvidenceStore. Refused transitions raise IllegalTransitionError
with a specific reason and record nothing.
"""

from __future__ import annotations

from typing import Any

from . import validate as _validate
from .evidence import EvidenceStore
from .util import new_evidence_id, now_rfc3339

PRIMARY_CHAIN: tuple[str, ...] = (
    "INTAKE",
    "DESIGN_READY",
    "IMPLEMENTATION_READY",
    "BUILT",
    "BASELINED",
    "TESTED",
    "TRIAGED",
    "RECONCILING",
    "CORRECTED",
    "REGRESSION_VERIFIED",
    "ACCEPTANCE_READY",
    "RELEASED",
)

SIDE_STATES: frozenset[str] = frozenset(
    {"WAITING_FOR_INPUT", "BLOCKED", "FAILED", "CANCELLED", "SUPERSEDED"}
)

TERMINAL_STATES: frozenset[str] = frozenset({"RELEASED", "CANCELLED", "SUPERSEDED"})

ALL_STATES: frozenset[str] = frozenset(PRIMARY_CHAIN) | SIDE_STATES

_NEXT: dict[str, str | None] = {
    state: (PRIMARY_CHAIN[i + 1] if i + 1 < len(PRIMARY_CHAIN) else None)
    for i, state in enumerate(PRIMARY_CHAIN)
}


class IllegalTransitionError(Exception):
    """Raised when a transition is refused; carries the specific reason."""

    def __init__(self, from_state: str, to_state: str, reason: str):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(f"illegal transition {from_state} -> {to_state}: {reason}")


class CycleMachine:
    """A cycle record plus its guarded state machine.

    The machine holds the cycle's current state in memory; the durable
    record of every move is the evidence store. The cycle record passed
    in is validated against the WP2 cycle schema at construction.
    """

    def __init__(
        self,
        store: EvidenceStore,
        cycle: dict[str, Any],
        *,
        actor: str = "radpipe-statemachine",
    ):
        _validate.validate(cycle, "cycle")
        self.store = store
        self.cycle: dict[str, Any] = dict(cycle)
        self.actor = actor
        self.attempt = 1
        # The primary-lifecycle state a side state returns to. Starts at
        # the cycle's own state if it begins in a side state (degenerate;
        # such a cycle can only be cancelled/superseded or advanced once
        # an operator supplies a resume target out of band).
        self._resume_state: str | None = (
            cycle["state"] if cycle["state"] in PRIMARY_CHAIN else None
        )

    # -- introspection -------------------------------------------------

    @property
    def state(self) -> str:
        return self.cycle["state"]

    @property
    def cycle_id(self) -> str:
        return self.cycle["cycle_id"]

    def legal_targets(self) -> set[str]:
        """States reachable from the current state (guards aside)."""
        current = self.state
        if current in TERMINAL_STATES:
            return set()
        targets: set[str] = set()
        nxt = _NEXT.get(current)
        if nxt is not None:
            targets.add(nxt)
        # Side states may be entered from any non-terminal state.
        targets |= {"WAITING_FOR_INPUT", "BLOCKED", "FAILED", "CANCELLED", "SUPERSEDED"}
        if current in SIDE_STATES and self._resume_state is not None:
            targets.add(self._resume_state)
        targets.discard(current)
        return targets

    def can_transition(self, to_state: str) -> bool:
        return to_state in self.legal_targets()

    # -- the guard -----------------------------------------------------

    def _check(
        self,
        to_state: str,
        *,
        reason: str | None,
        decision_ref: str | None,
        verification_ref: str | None,
        successor_cycle_id: str | None,
        authorization_ref: str | None,
    ) -> None:
        current = self.state
        if to_state not in ALL_STATES:
            raise IllegalTransitionError(current, to_state, f"unknown state {to_state!r}")
        if to_state == current:
            raise IllegalTransitionError(current, to_state, "already in this state")
        if current in TERMINAL_STATES:
            raise IllegalTransitionError(
                current, to_state, f"{current} is terminal; no outgoing transitions"
            )

        if current in SIDE_STATES and to_state not in SIDE_STATES:
            # Returning from a side state: only to the state it was
            # entered from, and only with that side state's guard met.
            if to_state != self._resume_state:
                raise IllegalTransitionError(
                    current,
                    to_state,
                    f"from {current} the only return target is "
                    f"{self._resume_state!r} (the state it was entered from)",
                )
            if current == "WAITING_FOR_INPUT" and not decision_ref:
                raise IllegalTransitionError(
                    current,
                    to_state,
                    "WAITING_FOR_INPUT returns only when the referenced "
                    "decision is recorded (decision_ref required)",
                )
            if current == "BLOCKED" and not verification_ref:
                raise IllegalTransitionError(
                    current,
                    to_state,
                    "BLOCKED returns only when the prerequisite is "
                    "independently verified (verification_ref required)",
                )
            return

        if to_state in SIDE_STATES:
            if to_state == "SUPERSEDED":
                if not successor_cycle_id:
                    raise IllegalTransitionError(
                        current,
                        to_state,
                        "SUPERSEDED requires a successor cycle reference "
                        "(successor_cycle_id required)",
                    )
            elif not reason:
                raise IllegalTransitionError(
                    current,
                    to_state,
                    f"entering {to_state} requires a reason",
                )
            return

        # Primary-to-primary: only the next link in the chain.
        expected = _NEXT.get(current)
        if to_state != expected:
            raise IllegalTransitionError(
                current,
                to_state,
                f"the lifecycle advances {current} -> {expected}; "
                f"{to_state} is not the next state",
            )
        if to_state == "RELEASED" and not authorization_ref:
            raise IllegalTransitionError(
                current,
                to_state,
                "RELEASED requires explicit release authority "
                "(authorization_ref required)",
            )

    # -- transitions ---------------------------------------------------

    def transition(
        self,
        to_state: str,
        *,
        actor: str | None = None,
        reason: str | None = None,
        decision_ref: str | None = None,
        verification_ref: str | None = None,
        successor_cycle_id: str | None = None,
        authorization_ref: str | None = None,
        summary: str | None = None,
    ) -> dict:
        """Attempt a transition; on success record evidence, return its envelope."""
        self._check(
            to_state,
            reason=reason,
            decision_ref=decision_ref,
            verification_ref=verification_ref,
            successor_cycle_id=successor_cycle_id,
            authorization_ref=authorization_ref,
        )
        from_state = self.state
        if from_state in PRIMARY_CHAIN and to_state in SIDE_STATES:
            self._resume_state = from_state
        if from_state == "FAILED" and to_state not in SIDE_STATES:
            # A retry is a new attempt; prior evidence is untouched.
            self.attempt += 1
        self.cycle["state"] = to_state
        if to_state == "SUPERSEDED":
            self.cycle["successor_cycle_id"] = successor_cycle_id

        detail = summary or f"Cycle {self.cycle_id} transition {from_state} -> {to_state}."
        extras = [
            f"reason: {reason}" if reason else None,
            f"decision_ref: {decision_ref}" if decision_ref else None,
            f"verification_ref: {verification_ref}" if verification_ref else None,
            f"successor_cycle_id: {successor_cycle_id}" if successor_cycle_id else None,
            f"authorization_ref: {authorization_ref}" if authorization_ref else None,
            f"attempt: {self.attempt}",
        ]
        record = {
            "schema_version": "0.1",
            "evidence_id": new_evidence_id("EVD-TRN"),
            "cycle_id": self.cycle_id,
            "run_id": f"statemachine:{self.cycle_id}",
            "stage_id": "state-machine",
            "class": "VERIFIED",
            "source": "statemachine://rad-pipeline/cycle",
            "captured_at": now_rfc3339(),
            "actor": actor or self.actor,
            "summary": detail + " " + "; ".join(e for e in extras if e),
            "limitations": [],
            "related_artifact_ids": [],
        }
        return self.store.append(record)
