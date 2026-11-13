# WP3 — Orchestration core

Implements WP3 of `seed/docs/IMPLEMENTATION-PLAN.md`: declarative
DAG/task dependencies, the state machine and transition guard, bounded
parallel execution, timeout/cancellation/retry handling, idempotent
task/run identifiers, a safe subprocess allowlist with output capture,
and the policy gate interface.

Built on WP2, which is **not modified**: the WP2 `radpipe` package
(`validate.py`, `evidence.py`, `redact.py`) and `schemas/` were copied
into this tree and extended here. Environment: Python 3.12.3,
`jsonschema` 4.10.3 (as in WP2), stdlib `unittest`, `ThreadPoolExecutor`
for within-stage parallelism. Fully offline.

## Design stance (Kit's structured pipe)

Per `discovery/DESIGN-NOTES.md`, the scheduler is a **stage pipe first
and a graph second**: stages run strictly in declared pipe order;
parallelism happens only inside a stage, between tasks with no
interdependency, up to a configurable bound. Nothing enters or leaves
except through the pipe, and stage boundaries are where evidence is
written. At cycle close the pipe emits the next cycle's intake package
as a first-class output (the Möbius loop) instead of leaving an
operator to reassemble it.

## What was built

### `radpipe/statemachine.py` — cycle state machine + transition guard
`CycleMachine` wraps a WP2 cycle record. The primary chain from
STATE-MACHINE.md (INTAKE → … → RELEASED) advances one link at a time;
any other primary-to-primary move raises `IllegalTransitionError` with
the specific reason. Side-state rules are enforced as guards:
entering WAITING_FOR_INPUT / BLOCKED / FAILED / CANCELLED requires a
reason; SUPERSEDED requires `successor_cycle_id`; RELEASED requires an
`authorization_ref`; WAITING_FOR_INPUT returns only with a
`decision_ref`, BLOCKED only with a `verification_ref`, FAILED returns
as a new attempt (the attempt counter increments; prior evidence is
immutable). RELEASED / CANCELLED / SUPERSEDED are terminal. **Every
accepted transition appends an evidence record** via WP2's
`EvidenceStore`; refused transitions record nothing.

### `radpipe/scheduler.py` — stage-pipe scheduler
- Specs: `TaskSpec` (argv, `depends_on`, `timeout_s`, `retryable`,
  `idempotent`, `max_attempts`, `cwd`, `env`), `StageSpec` (ordered
  tasks, `kind`, named `gates`, policy `action`, declared `inputs`),
  `RunSpec` (run/cycle IDs, ordered stages, policy `flags`,
  `next_cycle_id`, `carry_findings`).
- **Fail-closed spec validation, before anything executes:** duplicate
  task IDs, unknown dependency IDs, dependencies on tasks in later
  stages (crossing the pipe backward), and dependency cycles within a
  stage each raise a specific `SpecError` subclass and nothing runs.
  Dependencies on same-stage tasks order execution; dependencies on
  earlier-stage tasks are already satisfied when the pipe arrives.
- Execution: stages in pipe order; within a stage, dependency-ready
  tasks run concurrently up to the scheduler's `parallel_bound`
  (tracked live and reported as `max_concurrency` per stage). A failed
  task's dependents (transitively) are **skipped**; independent tasks
  still run to completion, then the stage fails as a whole and the
  pipe stops.
- Evidence at stage boundaries: one evidence record per policy-gate
  evaluation, one per task **attempt** (command, verdict, output hash),
  and one WP2 **stage record** per executed stage (state, pipe linkage
  via `depends_on`, declared inputs, output evidence refs, policy
  decision ref).
- **Idempotent run IDs:** re-submitting the same `run_id` with the
  same spec fingerprint returns the stored `RunResult` without
  re-executing (the duplicate submission itself is evidenced); the
  same `run_id` with a different spec raises `RunIdConflictError`.
- **Cycle close:** on full completion, the next cycle's intake package
  — a WP2 cycle record in state INTAKE, seeded with the prior cycle's
  intent, baseline (carried as provenance), artifact inventory and
  open findings plus the run's `carry_findings` — is validated,
  appended to the evidence store, announced by a closing evidence
  record carrying its content hash, and its ID returned.

### `radpipe/executor.py` — safe subprocess execution
Structured argv only (`shell=False`, always). `argv[0]` must appear
verbatim on the executor's allowlist or the command is refused before
anything runs. Tasks start in their own process group; on timeout the
group is killed and the outcome is reported as timed out (never a
pass). stdout/stderr are captured and capped (default 64 KiB each);
truncation is flagged, not silent.

### `radpipe/policy.py` — policy gates
`GateRegistry` consults named gates before a stage runs. Fail-closed:
unregistered gate names, gates that raise, and malformed decisions are
all denials (CONTRACTS.md: "Unknown policy result is a deny"). A denial
blocks the stage before any task runs and is recorded in evidence.
Provided gates: `FlagGate` (a named precondition flag must hold an
exact value) and `CegGenerationGate` — the standing rule that CEG
generation is blocked until CEG-PARADIGM-CLEANUP is DONE, modelled as
the context flag `ceg_paradigm_cleanup == "DONE"`.

### Retry policy
A failed attempt is retried only when the task is declared **both**
`retryable` and `idempotent`, and only up to `max_attempts`. Tasks are
non-idempotent unless declared idempotent, so the default is a single
attempt; a `retryable=True, idempotent=False` task runs exactly once.
Allowlist refusals are never retried (they occur before execution).

## Tests

Run (offline, from this directory):

```
cd ~/workspace/rad-pipeline/work/wp3
python3 -m unittest discover -s tests -v
```

Result on 2026-11-12 (this VM), two consecutive runs, identical:

```
Ran 45 tests in ~5.3s
OK
```

Breakdown: `test_statemachine.py` 9 (full chain walk, release
authorization guard, illegal jump refused with nothing recorded,
unknown/same state, side-state reason requirement, BLOCKED return
guard, WAITING_FOR_INPUT decision guard, FAILED retry attempt
counter, SUPERSEDED successor requirement + terminal states);
`test_policy.py` 6 (FlagGate, CEG gate states, unknown/raising/
malformed gates all deny, evaluate_all); `test_executor.py` 5
(capture, allowlist refusal, exit-code passthrough, timeout kill,
output cap); `test_scheduler.py` 25 (pipe order, within-stage
dependency order, earlier-stage dependency allowed, stage records with
pipe linkage; unknown dep / cycle / self-cycle / backward dep /
duplicate ID / wrong cycle all refused before execution; parallelism
bound respected *and* reached at bound 2, serialization at bound 1 —
measured by an flock-guarded probe the tasks themselves run, not by
timing; gate denial blocks + is evidenced, gate pass with cleanup
DONE, unknown gate denies; retry stops at cap with one evidence record
per attempt, no retry for non-idempotent or non-retryable tasks,
retry-then-succeed; timeout cancels a 30 s task at 0.5 s with its
post-sleep marker never written; allowlist refusal with zero attempts;
dependent-of-failure skipped while an independent task still runs;
duplicate run ID returns the same result without re-executing, run-ID
reuse with a different spec refused; cycle close emits a schema-valid
INTAKE record carrying open + carried findings, failed run emits
none). Test helpers live in `tests/helpers/` (marker, fail,
fail-N-times counter, sleep, concurrency probe).

## Provisional choices and open questions for the owner

Choices forced by WP2's open questions or spec silence — each is
**provisional**, named here rather than silently baked in:

- **P1 (extends WP2 Q1 — stage-state vocabulary).** No stage-state
  enum exists in the specs. Stage records written by the scheduler use
  `"completed"`, `"failed"`, `"blocked"`. (WP2's own stage fixture
  used `"completed"`, so at least that value has precedent.)
- **P2 (side-state return target).** STATE-MACHINE.md says
  WAITING_FOR_INPUT / BLOCKED "return only when …" without naming the
  destination. Implemented as: return to the primary state the side
  state was entered from, and to no other state. Entering a second
  side state from a side state does not change the return target.
- **P3 (FAILED return).** "FAILED may retry as a new attempt" is
  implemented as a return to the state FAILED was entered from, with
  the machine's attempt counter incremented and the attempt number
  written into the transition evidence summary.

Numbered questions where the specs are silent (no semantics invented):

- **Q1. Within-stage failure semantics.** When one task in a stage
  fails, independent sibling tasks currently still run to completion
  (more evidence) and only dependents are skipped. The alternative —
  stop starting new work at the first failure — is equally consistent
  with the texts. Which does the owner want as the pipe's rule?
- **Q2. Meaning of "cross stages backward".** Implemented as:
  dependencies on earlier-stage tasks are legal and pre-satisfied;
  dependencies on later-stage tasks are refused. If instead *all*
  cross-stage task dependencies should be refused (pipe purity: a
  stage may depend only on the previous stage as a whole), say so and
  the validator tightens.
- **Q3. Stage-level attempts.** Stage records always carry
  `attempt: 1`; retries exist only at task level. Should a re-run of a
  whole stage (same run, new attempt) be a scheduler concept, or is a
  stage retry always a new run?
- **Q4. Run-ID registry persistence.** Idempotency is kept in memory
  per `Scheduler` instance. Across processes it would need a durable
  registry (e.g. derived from the evidence store). Is in-memory
  acceptable for the MVP, or must duplicate detection survive a
  runner restart?
- **Q5. Transition evidence addressing.** Evidence records require
  `run_id` and `stage_id`; state transitions have neither, so they are
  recorded with `stage_id: "state-machine"` and
  `run_id: "statemachine:<cycle_id>"`. Should transitions instead be
  their own record kind with a WP2 schema addition?
- **Q6. Release authorization mechanics.** The RELEASED guard takes an
  `authorization_ref` string (e.g. an approval record's ID). Should
  the machine instead consult the policy registry / an approval
  record and verify it, rather than trusting a supplied reference?
- **Q7. CEG gate flag provenance.** `CegGenerationGate` reads the
  context flag `ceg_paradigm_cleanup` from the run spec's `flags`.
  Who sets that flag in production — the project adapter (WP4) reading
  the cleanup task's state from the queue? The gate trusts the flag as
  supplied; nothing here verifies it against a source.
- **Q8. Raw task output retention.** Attempt evidence stores the
  command, verdict, sizes and a SHA-256 of stdout/stderr, but the raw
  output itself is not persisted (WP2 evidence supports
  `raw_output_ref`). Where should raw output live — files beside the
  evidence store, referenced per attempt?
- **Q9. Next-cycle identity defaults.** When a run doesn't name the
  next cycle, the ID is derived by incrementing the trailing number
  of the current `cycle_id` (`...-001` → `...-002`), `approval_refs`
  reset to empty, and the baseline carried verbatim. Should approvals
  ever carry over, and should the baseline be re-resolved rather than
  inherited on the Möbius turn?
- **Q10. Timeouts of idempotent tasks.** A timed-out attempt counts as
  a failed attempt and is retried when the task is retry-eligible.
  Is retrying after a timeout — where the original work may partially
  have happened — within the meaning of the owner's idempotency
  declaration, or should timeouts never retry?
