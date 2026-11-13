"""Stage-pipe scheduler (WP3) — DESIGN-NOTES.md as executable structure.

Kit's design (2026-11-12 clarification): a structured pipe — "records
enter one end, pass through a fixed sequence of declared processing
stages, and exit transformed". The scheduler is therefore a stage pipe
first and a graph second:

- A cycle is an ORDERED list of stages; stages run strictly in pipe
  order. A stage starts only after the previous stage completed.
- Parallelism happens only INSIDE a stage (independent tasks ground
  concurrently, up to a configurable bound) — never by reordering
  stages or letting a stage improvise routing.
- Tasks declare dependencies by ID. A dependency may name a task in
  the same stage (orders execution within the stage) or in an earlier
  stage (already satisfied when the pipe arrives). Anything else
  fails closed before any task runs: unknown dependency IDs, duplicate
  task IDs, dependencies on later stages ("crossing stages backward"),
  and cycles in a stage's dependency graph all raise SpecError
  subclasses and nothing executes.
- Stage boundaries are where evidence is written: policy decisions,
  every task attempt, and a WP2 stage record per executed stage.

Retry policy (CONTRACTS.md: "do not automatically replay
non-idempotent requests"): a failed attempt is retried only when the
task is declared BOTH retryable and idempotent, and only up to its
max_attempts cap. Tasks are non-idempotent unless declared idempotent,
so the default is: run once.

Idempotent run identifiers: submitting the same run_id with the same
spec returns the stored RunResult without executing anything again;
the same run_id with a different spec is refused (RunIdConflictError).

Cycle close (the Möbius loop): when every stage completes, the
scheduler emits the next cycle's intake package — a WP2 cycle record
in state INTAKE, seeded from this cycle's intent, baseline (carried as
provenance), artifact inventory and open findings — into the evidence
store, and returns its cycle_id on the RunResult.

PROVISIONAL (WP2 open question Q1: no stage-state vocabulary exists in
the specs): stage records use the states "completed", "failed" and
"blocked". Stage-record attempt is always 1; retries live at task
level, where attempt records are per-attempt evidence.
"""

from __future__ import annotations

import hashlib
import re
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any

from . import validate as _validate
from .evidence import EvidenceStore, canonical_bytes, content_hash
from .executor import CommandNotAllowedError, Executor, TaskOutcome
from .policy import GateDecision, GateRegistry
from .util import new_evidence_id, now_rfc3339

STAGE_KINDS = (
    "design", "build", "test", "audit", "reconcile",
    "correction", "regression", "acceptance", "release",
)


# ---------------------------------------------------------------- specs

@dataclass
class TaskSpec:
    task_id: str
    argv: list[str]
    depends_on: tuple[str, ...] = ()
    timeout_s: float = 60.0
    retryable: bool = False
    idempotent: bool = False  # non-idempotent unless declared idempotent
    max_attempts: int = 1
    cwd: str | None = None
    env: dict[str, str] | None = None

    @property
    def retry_eligible(self) -> bool:
        return self.retryable and self.idempotent

    @property
    def effective_max_attempts(self) -> int:
        return self.max_attempts if self.retry_eligible else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "argv": list(self.argv),
            "depends_on": list(self.depends_on),
            "timeout_s": self.timeout_s,
            "retryable": self.retryable,
            "idempotent": self.idempotent,
            "max_attempts": self.max_attempts,
            "cwd": self.cwd,
            "env": self.env,
        }


@dataclass
class StageSpec:
    stage_id: str
    tasks: list[TaskSpec]
    kind: str = "test"
    gates: tuple[str, ...] = ()
    action: str | None = None  # policy context; defaults to kind
    inputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "kind": self.kind,
            "gates": list(self.gates),
            "action": self.action,
            "inputs": list(self.inputs),
            "tasks": [t.to_dict() for t in self.tasks],
        }


@dataclass
class RunSpec:
    run_id: str
    cycle_id: str
    stages: list[StageSpec]
    flags: dict[str, Any] = field(default_factory=dict)
    next_cycle_id: str | None = None
    carry_findings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "cycle_id": self.cycle_id,
            "flags": self.flags,
            "next_cycle_id": self.next_cycle_id,
            "carry_findings": list(self.carry_findings),
            "stages": [s.to_dict() for s in self.stages],
        }

    def fingerprint(self) -> str:
        return content_hash(self.to_dict())


# ---------------------------------------------------------------- errors

class SpecError(Exception):
    """The run spec is invalid; nothing was executed (fail closed)."""


class UnknownDependencyError(SpecError):
    pass


class BackwardDependencyError(SpecError):
    pass


class DependencyCycleError(SpecError):
    pass


class DuplicateTaskError(SpecError):
    pass


class RunIdConflictError(SpecError):
    pass


# ---------------------------------------------------------------- results

@dataclass
class TaskResult:
    task_id: str
    stage_id: str
    status: str  # succeeded | failed | timed_out | skipped
    attempts: int = 0
    exit_codes: list[int | None] = field(default_factory=list)
    error: str | None = None
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class StageResult:
    stage_id: str
    status: str  # completed | failed | blocked
    tasks: dict[str, TaskResult] = field(default_factory=dict)
    gate_decisions: list[GateDecision] = field(default_factory=list)
    max_concurrency: int = 0
    policy_decision_ref: str | None = None
    output_refs: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    run_id: str
    cycle_id: str
    status: str  # completed | failed | blocked
    stages: list[StageResult] = field(default_factory=list)
    next_cycle_id: str | None = None
    duplicate: bool = False


# ---------------------------------------------------------------- scheduler

class Scheduler:
    """Executes RunSpecs for one cycle, writing evidence as it goes."""

    def __init__(
        self,
        store: EvidenceStore,
        cycle: dict[str, Any],
        executor: Executor,
        registry: GateRegistry | None = None,
        *,
        parallel_bound: int = 4,
        actor: str = "radpipe-scheduler",
    ):
        _validate.validate(cycle, "cycle")
        if parallel_bound < 1:
            raise SpecError(f"parallel_bound must be >= 1, got {parallel_bound}")
        self.store = store
        self.cycle = dict(cycle)
        self.executor = executor
        self.registry = registry if registry is not None else GateRegistry()
        self.parallel_bound = parallel_bound
        self.actor = actor
        self._store_lock = threading.Lock()
        self._runs: dict[str, tuple[str, RunResult]] = {}

    # -- evidence helpers (serialized: the store is append-only) -------

    def _append(self, record: dict[str, Any], *, kind: str | None = None) -> dict:
        """Append a record; non-evidence kinds are validated by the caller
        against their own schema first, then stored with validate=False."""
        with self._store_lock:
            if kind is None:
                return self.store.append(record)
            _validate.validate(record, kind)
            return self.store.append(record, validate=False)

    def _evidence(
        self,
        *,
        prefix: str,
        run_id: str,
        stage_id: str,
        summary: str,
        source: str,
        sha256: str | None = None,
        evidence_class: str = "DEMONSTRATED",
    ) -> str:
        record: dict[str, Any] = {
            "schema_version": "0.1",
            "evidence_id": new_evidence_id(prefix),
            "cycle_id": self.cycle["cycle_id"],
            "run_id": run_id,
            "stage_id": stage_id,
            "class": evidence_class,
            "source": source,
            "captured_at": now_rfc3339(),
            "actor": self.actor,
            "summary": summary,
            "limitations": [],
            "related_artifact_ids": [],
        }
        if sha256 is not None:
            record["sha256"] = sha256
        envelope = self._append(record)
        return envelope["record"]["evidence_id"]

    # -- spec validation (fail closed, before anything runs) -----------

    def _validate_spec(self, spec: RunSpec) -> dict[str, int]:
        """Return {task_id: stage_index}; raise SpecError on any defect."""
        if spec.cycle_id != self.cycle["cycle_id"]:
            raise SpecError(
                f"run targets cycle {spec.cycle_id!r} but this scheduler serves "
                f"cycle {self.cycle['cycle_id']!r}"
            )
        if not spec.stages:
            raise SpecError("run has no stages")
        task_stage: dict[str, int] = {}
        for index, stage in enumerate(spec.stages):
            if stage.kind not in STAGE_KINDS:
                raise SpecError(
                    f"stage {stage.stage_id!r}: unknown kind {stage.kind!r}; "
                    f"expected one of {list(STAGE_KINDS)}"
                )
            for task in stage.tasks:
                if task.task_id in task_stage:
                    raise DuplicateTaskError(
                        f"task_id {task.task_id!r} is declared more than once; "
                        "dependency IDs must be unambiguous"
                    )
                if not task.argv:
                    raise SpecError(f"task {task.task_id!r}: argv must not be empty")
                if task.timeout_s <= 0:
                    raise SpecError(
                        f"task {task.task_id!r}: timeout_s must be > 0, "
                        f"got {task.timeout_s}"
                    )
                if task.max_attempts < 1:
                    raise SpecError(
                        f"task {task.task_id!r}: max_attempts must be >= 1, "
                        f"got {task.max_attempts}"
                    )
                task_stage[task.task_id] = index
        for index, stage in enumerate(spec.stages):
            for task in stage.tasks:
                for dep in task.depends_on:
                    if dep not in task_stage:
                        raise UnknownDependencyError(
                            f"task {task.task_id!r} depends on unknown task {dep!r}"
                        )
                    if task_stage[dep] > index:
                        raise BackwardDependencyError(
                            f"task {task.task_id!r} (stage {stage.stage_id!r}) depends "
                            f"on {dep!r} in a later stage; dependencies may only "
                            "point within the stage or backward in the pipe"
                        )
        # Cycle detection within each stage's same-stage dependency graph.
        for stage in spec.stages:
            same = {
                t.task_id: [d for d in t.depends_on if task_stage[d] == task_stage[t.task_id]]
                for t in stage.tasks
            }
            visiting, done = set(), set()

            def visit(node: str, trail: list[str]) -> None:
                if node in done:
                    return
                if node in visiting:
                    cycle_path = " -> ".join(trail + [node])
                    raise DependencyCycleError(
                        f"dependency cycle in stage {stage.stage_id!r}: {cycle_path}"
                    )
                visiting.add(node)
                for dep in same[node]:
                    visit(dep, trail + [node])
                visiting.discard(node)
                done.add(node)

            for task_id in same:
                visit(task_id, [])
        return task_stage

    # -- public entry point ---------------------------------------------

    def run(self, spec: RunSpec) -> RunResult:
        fingerprint = spec.fingerprint()
        prior = self._runs.get(spec.run_id)
        if prior is not None:
            prior_fingerprint, prior_result = prior
            if prior_fingerprint != fingerprint:
                raise RunIdConflictError(
                    f"run_id {spec.run_id!r} was already submitted with a "
                    "different spec; refusing to execute under a reused ID"
                )
            self._evidence(
                prefix="EVD-DUP",
                run_id=spec.run_id,
                stage_id="scheduler",
                summary=(
                    f"Duplicate submission of run {spec.run_id} with an identical "
                    "spec; returned the existing run without re-executing."
                ),
                source="scheduler://rad-pipeline/idempotency",
            )
            prior_result.duplicate = True
            return prior_result

        self._validate_spec(spec)
        result = RunResult(run_id=spec.run_id, cycle_id=spec.cycle_id, status="completed")
        previous_stage_id: str | None = None
        for stage in spec.stages:
            stage_result = self._run_stage(spec, stage, previous_stage_id)
            result.stages.append(stage_result)
            previous_stage_id = stage.stage_id
            if stage_result.status != "completed":
                result.status = stage_result.status  # "failed" or "blocked"
                break
        if result.status == "completed":
            result.next_cycle_id = self._close_cycle(spec, result)
        self._runs[spec.run_id] = (fingerprint, result)
        return result

    # -- one stage of the pipe -------------------------------------------

    def _run_stage(
        self, spec: RunSpec, stage: StageSpec, previous_stage_id: str | None
    ) -> StageResult:
        started_at = now_rfc3339()
        stage_result = StageResult(stage_id=stage.stage_id, status="completed")

        # Policy gates first: a denial fails the stage closed, before
        # any task runs, and the denial is evidenced.
        context = {
            "project_id": self.cycle["project_id"],
            "cycle_id": spec.cycle_id,
            "run_id": spec.run_id,
            "stage_id": stage.stage_id,
            "action": stage.action or stage.kind,
            "flags": dict(spec.flags),
        }
        decisions = self.registry.evaluate_all(list(stage.gates), context)
        stage_result.gate_decisions = decisions
        for decision in decisions:
            evidence_id = self._evidence(
                prefix="EVD-POL",
                run_id=spec.run_id,
                stage_id=stage.stage_id,
                summary=(
                    f"Policy gate {decision.gate!r} "
                    f"{'ALLOWED' if decision.allowed else 'DENIED'} stage "
                    f"{stage.stage_id!r}: {decision.reason}"
                ),
                source=f"policy://{decision.gate}",
                evidence_class="VERIFIED",
            )
            stage_result.output_refs.append(f"evidence://{evidence_id}")
            if stage_result.policy_decision_ref is None:
                stage_result.policy_decision_ref = f"evidence://{evidence_id}"
        if any(not d.allowed for d in decisions):
            stage_result.status = "blocked"
            self._write_stage_record(
                spec, stage, stage_result,
                started_at=started_at, completed_at=now_rfc3339(),
                previous_stage_id=previous_stage_id,
            )
            return stage_result

        # Execute the stage's tasks: pipe order inside the stage is set
        # by dependencies; independent tasks ground concurrently.
        self._execute_stage_tasks(spec, stage, stage_result)
        for task_result in stage_result.tasks.values():
            for evidence_id in task_result.evidence_ids:
                stage_result.output_refs.append(f"evidence://{evidence_id}")
        if any(t.status != "succeeded" for t in stage_result.tasks.values()):
            stage_result.status = "failed"
        self._write_stage_record(
            spec, stage, stage_result,
            started_at=started_at, completed_at=now_rfc3339(),
            previous_stage_id=previous_stage_id,
        )
        return stage_result

    def _execute_stage_tasks(
        self, spec: RunSpec, stage: StageSpec, stage_result: StageResult
    ) -> None:
        same_stage_deps: dict[str, list[str]] = {}
        stage_task_ids = {t.task_id for t in stage.tasks}
        for task in stage.tasks:
            same_stage_deps[task.task_id] = [
                d for d in task.depends_on if d in stage_task_ids
            ]
            stage_result.tasks[task.task_id] = TaskResult(
                task_id=task.task_id, stage_id=stage.stage_id, status="skipped"
            )

        lock = threading.Lock()
        live = {"current": 0, "max": 0}

        def execute(task: TaskSpec) -> TaskResult:
            with lock:
                live["current"] += 1
                live["max"] = max(live["max"], live["current"])
            try:
                return self._run_task(spec, stage, task)
            finally:
                with lock:
                    live["current"] -= 1

        pending: dict[str, TaskSpec] = {t.task_id: t for t in stage.tasks}
        running: dict[Future, str] = {}
        finished: dict[str, str] = {}  # task_id -> final status

        with ThreadPoolExecutor(max_workers=self.parallel_bound) as pool:
            while pending or running:
                # Tasks whose dependencies failed (or were skipped) are
                # skipped without running; propagate transitively.
                # Independent tasks are unaffected: a stage gathers all
                # its independent results, then fails as a whole.
                progressed = True
                while progressed:
                    progressed = False
                    for task_id, task in list(pending.items()):
                        deps = same_stage_deps[task_id]
                        if any(finished.get(d) in ("failed", "timed_out", "skipped")
                               for d in deps):
                            finished[task_id] = "skipped"
                            del pending[task_id]
                            progressed = True
                # Submit runnable tasks up to the parallelism bound.
                for task_id, task in list(pending.items()):
                    if len(running) >= self.parallel_bound:
                        break
                    if all(finished.get(d) == "succeeded"
                           for d in same_stage_deps[task_id]):
                        future = pool.submit(execute, task)
                        running[future] = task_id
                        del pending[task_id]
                if not running:
                    # Nothing in flight and nothing submittable: any
                    # remaining pending tasks are blocked by failures.
                    for task_id in list(pending):
                        finished[task_id] = "skipped"
                        del pending[task_id]
                    break
                done_futures, _ = wait(running.keys(), return_when=FIRST_COMPLETED)
                for future in done_futures:
                    task_id = running.pop(future)
                    task_result = future.result()
                    stage_result.tasks[task_id] = task_result
                    finished[task_id] = task_result.status
        stage_result.max_concurrency = live["max"]

    def _run_task(self, spec: RunSpec, stage: StageSpec, task: TaskSpec) -> TaskResult:
        result = TaskResult(task_id=task.task_id, stage_id=stage.stage_id, status="failed")
        try:
            self.executor.check_allowed(task.argv)
        except CommandNotAllowedError as exc:
            result.error = str(exc)
            evidence_id = self._evidence(
                prefix="EVD-TSK",
                run_id=spec.run_id,
                stage_id=stage.stage_id,
                summary=f"Task {task.task_id!r} refused before execution: {exc}",
                source="executor://rad-pipeline/allowlist",
            )
            result.evidence_ids.append(evidence_id)
            return result

        attempts_allowed = task.effective_max_attempts
        for attempt in range(1, attempts_allowed + 1):
            try:
                outcome = self.executor.run(
                    task.argv, timeout_s=task.timeout_s, cwd=task.cwd, env=task.env
                )
            except CommandNotAllowedError as exc:  # allowlist changed mid-run
                result.error = str(exc)
                return result
            result.attempts = attempt
            result.exit_codes.append(outcome.exit_code)
            evidence_id = self._attempt_evidence(spec, stage, task, attempt, outcome)
            result.evidence_ids.append(evidence_id)
            if outcome.succeeded:
                result.status = "succeeded"
                result.error = None
                return result
            result.status = "timed_out" if outcome.timed_out else "failed"
            result.error = outcome.error
        return result

    def _attempt_evidence(
        self,
        spec: RunSpec,
        stage: StageSpec,
        task: TaskSpec,
        attempt: int,
        outcome: TaskOutcome,
    ) -> str:
        command = " ".join(task.argv)
        if outcome.timed_out:
            verdict = f"TIMED OUT after {task.timeout_s}s and was killed"
        elif outcome.error is not None:
            verdict = f"failed to execute: {outcome.error}"
        else:
            verdict = f"exit code {outcome.exit_code}"
        summary = (
            f"Task {task.task_id!r} attempt {attempt}: `{command}` -> {verdict}. "
            f"stdout {len(outcome.stdout)} chars, stderr {len(outcome.stderr)} chars"
            + (" (output truncated at cap)" if outcome.truncated else "")
            + "."
        )
        output_hash = hashlib.sha256(
            canonical_bytes(
                {"stdout": outcome.stdout, "stderr": outcome.stderr,
                 "exit_code": outcome.exit_code, "timed_out": outcome.timed_out}
            )
        ).hexdigest()
        return self._evidence(
            prefix="EVD-TSK",
            run_id=spec.run_id,
            stage_id=stage.stage_id,
            summary=summary,
            source=f"command://{task.argv[0]}",
            sha256=output_hash,
        )

    # -- stage record ----------------------------------------------------

    def _write_stage_record(
        self,
        spec: RunSpec,
        stage: StageSpec,
        stage_result: StageResult,
        *,
        started_at: str,
        completed_at: str,
        previous_stage_id: str | None,
    ) -> None:
        record = {
            "schema_version": "0.1",
            "stage_id": stage.stage_id,
            "cycle_id": spec.cycle_id,
            "run_id": spec.run_id,
            "attempt": 1,
            "kind": stage.kind,
            "state": stage_result.status,
            "depends_on": [previous_stage_id] if previous_stage_id else [],
            "inputs": list(stage.inputs),
            "outputs": list(stage_result.output_refs),
            "actor": self.actor,
            "started_at": started_at,
            "completed_at": completed_at,
            "policy_decision_ref": stage_result.policy_decision_ref,
        }
        self._append(record, kind="stage")

    # -- cycle close: the Möbius loop ------------------------------------

    def _close_cycle(self, spec: RunSpec, result: RunResult) -> str:
        cycle = self.cycle
        next_cycle_id = spec.next_cycle_id or _default_next_cycle_id(cycle["cycle_id"])
        output_refs = [
            ref for stage in result.stages for ref in stage.output_refs
        ]
        intent = (
            f"Continuation of cycle {cycle['cycle_id']} (run {spec.run_id} "
            "completed). Original intent: "
            f"{cycle['intent']} Prior-cycle stage outputs: "
            + (", ".join(output_refs) if output_refs else "none recorded")
            + "."
        )
        next_cycle = {
            "schema_version": "0.1",
            "project_id": cycle["project_id"],
            "cycle_id": next_cycle_id,
            "created_at": now_rfc3339(),
            "intent": intent,
            "baseline": cycle["baseline"],  # carried as provenance
            "state": "INTAKE",
            "policy_profile": cycle["policy_profile"],
            "artifact_inventory_ref": cycle["artifact_inventory_ref"],
            "approval_refs": [],
            "open_findings": list(cycle["open_findings"]) + list(spec.carry_findings),
        }
        # Validated against the cycle schema, then appended to the
        # ledger (the strip's surface) as a first-class record.
        self._append(next_cycle, kind="cycle")
        self._evidence(
            prefix="EVD-CLS",
            run_id=spec.run_id,
            stage_id="cycle-close",
            summary=(
                f"Cycle {cycle['cycle_id']} closed: run {spec.run_id} completed "
                f"all stages. Next-cycle intake package emitted as cycle "
                f"{next_cycle_id} in state INTAKE, seeded from this cycle's "
                "outputs and open findings."
            ),
            source="scheduler://rad-pipeline/cycle-close",
            sha256=content_hash(next_cycle),
        )
        return next_cycle_id


def _default_next_cycle_id(cycle_id: str) -> str:
    match = re.match(r"^(.*?)(\d+)$", cycle_id)
    if match:
        head, digits = match.groups()
        return f"{head}{int(digits) + 1:0{len(digits)}d}"
    return f"{cycle_id}-next"
