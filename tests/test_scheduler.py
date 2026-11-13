"""Scheduler tests (WP3): pipe order, parallelism bound, fail-closed
spec validation, gates, retries, timeout, idempotent run IDs, and the
cycle-close intake package. Fully offline and deterministic: helper
scripts record exactly what executed, and pass/fail never depends on
measuring elapsed time."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radpipe import validate
from radpipe.evidence import EvidenceStore
from radpipe.executor import Executor
from radpipe.policy import CegGenerationGate, GateRegistry
from radpipe.scheduler import (
    BackwardDependencyError,
    DependencyCycleError,
    DuplicateTaskError,
    RunIdConflictError,
    RunSpec,
    Scheduler,
    SpecError,
    StageSpec,
    TaskSpec,
    UnknownDependencyError,
)

PY = sys.executable
HELPERS = Path(__file__).resolve().parent / "helpers"


def make_cycle():
    return {
        "schema_version": "0.1",
        "project_id": "bibleapp",
        "cycle_id": "bibleapp-2026-11-12-001",
        "created_at": "2026-11-12T09:00:00Z",
        "intent": "Scheduler test cycle.",
        "baseline": {"status": "pending"},
        "state": "INTAKE",
        "policy_profile": "nonprod-default",
        "artifact_inventory_ref": "inventory://bibleapp/test",
        "approval_refs": [],
        "open_findings": ["FND-20261112-001"],
    }


class SchedulerTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = EvidenceStore(self.root / "evidence.jsonl")
        self.executor = Executor({PY})
        self.marker = self.root / "marker.txt"

    def tearDown(self):
        self.tmp.cleanup()

    def scheduler(self, bound=4, registry=None):
        return Scheduler(
            self.store, make_cycle(), self.executor,
            registry if registry is not None else GateRegistry(),
            parallel_bound=bound,
        )

    def marker_task(self, task_id, tag=None, **kwargs):
        return TaskSpec(
            task_id=task_id,
            argv=[PY, str(HELPERS / "marker.py"), str(self.marker), tag or task_id],
            **kwargs,
        )

    def marker_lines(self):
        if not self.marker.exists():
            return []
        return self.marker.read_text(encoding="utf-8").splitlines()

    def records(self):
        return self.store.records()

    def cycle_records(self):
        return [r for r in self.records() if "intent" in r]

    def stage_records(self):
        return [r for r in self.records() if "kind" in r and "depends_on" in r]


class TestPipeOrder(SchedulerTestBase):
    def test_stages_run_in_pipe_order(self):
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("build", [self.marker_task("b1", "build")], kind="build"),
            StageSpec("test", [self.marker_task("t1", "test")], kind="test"),
        ])
        result = self.scheduler().run(spec)
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.marker_lines(), ["build", "test"])

    def test_within_stage_dependency_orders_tasks(self):
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("test", [
                self.marker_task("b", depends_on=("a",)),
                self.marker_task("a"),
            ]),
        ])
        result = self.scheduler().run(spec)
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.marker_lines(), ["a", "b"])

    def test_dependency_on_earlier_stage_task_is_allowed(self):
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("build", [self.marker_task("compile", "compile")], kind="build"),
            StageSpec("test", [self.marker_task("smoke", "smoke", depends_on=("compile",))]),
        ])
        result = self.scheduler().run(spec)
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.marker_lines(), ["compile", "smoke"])

    def test_stage_records_written_with_pipe_linkage(self):
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("build", [self.marker_task("b1")], kind="build"),
            StageSpec("test", [self.marker_task("t1")], kind="test"),
        ])
        self.scheduler().run(spec)
        stages = self.stage_records()
        self.assertEqual([s["stage_id"] for s in stages], ["build", "test"])
        self.assertEqual([s["state"] for s in stages], ["completed", "completed"])
        self.assertEqual(stages[0]["depends_on"], [])
        self.assertEqual(stages[1]["depends_on"], ["build"])
        self.assertTrue(stages[1]["outputs"])  # task evidence refs
        self.assertTrue(self.store.verify().ok)


class TestFailClosedSpecValidation(SchedulerTestBase):
    def test_unknown_dependency_refused_before_anything_runs(self):
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("test", [self.marker_task("a", depends_on=("ghost",))]),
        ])
        with self.assertRaises(UnknownDependencyError):
            self.scheduler().run(spec)
        self.assertEqual(self.marker_lines(), [])
        self.assertEqual(self.records(), [])

    def test_dependency_cycle_refused(self):
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("test", [
                self.marker_task("a", depends_on=("b",)),
                self.marker_task("b", depends_on=("a",)),
            ]),
        ])
        with self.assertRaises(DependencyCycleError):
            self.scheduler().run(spec)
        # A self-dependency is a cycle too.
        spec2 = RunSpec("run-2", "bibleapp-2026-11-12-001", [
            StageSpec("test", [self.marker_task("a", depends_on=("a",))]),
        ])
        with self.assertRaises(DependencyCycleError):
            self.scheduler().run(spec2)
        self.assertEqual(self.marker_lines(), [])

    def test_backward_cross_stage_dependency_refused(self):
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("build", [self.marker_task("early", depends_on=("late",))], kind="build"),
            StageSpec("test", [self.marker_task("late")]),
        ])
        with self.assertRaises(BackwardDependencyError):
            self.scheduler().run(spec)
        self.assertEqual(self.marker_lines(), [])

    def test_duplicate_task_id_refused(self):
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("test", [self.marker_task("a"), self.marker_task("a")]),
        ])
        with self.assertRaises(DuplicateTaskError):
            self.scheduler().run(spec)

    def test_wrong_cycle_refused(self):
        spec = RunSpec("run-1", "some-other-cycle", [
            StageSpec("test", [self.marker_task("a")]),
        ])
        with self.assertRaises(SpecError):
            self.scheduler().run(spec)


class TestParallelismBound(SchedulerTestBase):
    def test_bound_respected_and_reached(self):
        state = self.root / "conc.json"
        tasks = [
            TaskSpec(f"p{i}", [PY, str(HELPERS / "conc_probe.py"), str(state), "1.0"])
            for i in range(4)
        ]
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [StageSpec("test", tasks)])
        result = self.scheduler(bound=2).run(spec)
        self.assertEqual(result.status, "completed")
        observed = json.loads(state.read_text(encoding="utf-8"))
        self.assertLessEqual(observed["max"], 2)   # the bound held
        self.assertGreaterEqual(observed["max"], 2)  # parallelism really happened
        self.assertEqual(observed["current"], 0)
        self.assertEqual(result.stages[0].max_concurrency, 2)

    def test_bound_one_serializes(self):
        state = self.root / "conc.json"
        tasks = [
            TaskSpec(f"p{i}", [PY, str(HELPERS / "conc_probe.py"), str(state), "0.4"])
            for i in range(3)
        ]
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [StageSpec("test", tasks)])
        result = self.scheduler(bound=1).run(spec)
        self.assertEqual(result.status, "completed")
        observed = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(observed["max"], 1)
        self.assertEqual(result.stages[0].max_concurrency, 1)


class TestPolicyGates(SchedulerTestBase):
    def registry(self):
        registry = GateRegistry()
        registry.register(CegGenerationGate())
        return registry

    def gated_spec(self, flags):
        return RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("generate", [self.marker_task("gen")],
                      kind="test", gates=("ceg-generation",), action="ceg_generation"),
        ], flags=flags)

    def test_gate_denial_blocks_stage_and_is_evidenced(self):
        result = self.scheduler(registry=self.registry()).run(self.gated_spec({}))
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.stages[0].status, "blocked")
        self.assertEqual(self.marker_lines(), [])  # the task never ran
        denials = [r for r in self.records()
                   if "DENIED" in r.get("summary", "") and "ceg-generation" in r["summary"]]
        self.assertEqual(len(denials), 1)
        stages = self.stage_records()
        self.assertEqual(stages[0]["state"], "blocked")
        self.assertIsNotNone(stages[0]["policy_decision_ref"])

    def test_gate_allows_when_cleanup_done(self):
        result = self.scheduler(registry=self.registry()).run(
            self.gated_spec({"ceg_paradigm_cleanup": "DONE"})
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.marker_lines(), ["gen"])

    def test_unknown_gate_denies(self):
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("test", [self.marker_task("a")], gates=("unregistered-gate",)),
        ])
        result = self.scheduler().run(spec)  # empty registry
        self.assertEqual(result.status, "blocked")
        self.assertEqual(self.marker_lines(), [])


class TestRetries(SchedulerTestBase):
    def counting_task(self, task_id, counter, failures, **kwargs):
        return TaskSpec(
            task_id=task_id,
            argv=[PY, str(HELPERS / "fail_times.py"), str(counter), str(failures)],
            **kwargs,
        )

    def test_retry_stops_at_cap(self):
        counter = self.root / "count.txt"
        task = self.counting_task("flaky", counter, 99,
                                  retryable=True, idempotent=True, max_attempts=3)
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [StageSpec("test", [task])])
        result = self.scheduler().run(spec)
        self.assertEqual(result.status, "failed")
        task_result = result.stages[0].tasks["flaky"]
        self.assertEqual(task_result.attempts, 3)
        self.assertEqual(counter.read_text(encoding="utf-8"), "3")
        self.assertEqual(len(task_result.evidence_ids), 3)  # one record per attempt

    def test_no_retry_for_non_idempotent_task(self):
        counter = self.root / "count.txt"
        task = self.counting_task("risky", counter, 99,
                                  retryable=True, idempotent=False, max_attempts=3)
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [StageSpec("test", [task])])
        result = self.scheduler().run(spec)
        self.assertEqual(result.stages[0].tasks["risky"].attempts, 1)
        self.assertEqual(counter.read_text(encoding="utf-8"), "1")

    def test_no_retry_when_not_declared_retryable(self):
        counter = self.root / "count.txt"
        task = self.counting_task("plain", counter, 99,
                                  retryable=False, idempotent=True, max_attempts=3)
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [StageSpec("test", [task])])
        result = self.scheduler().run(spec)
        self.assertEqual(result.stages[0].tasks["plain"].attempts, 1)

    def test_retry_eventually_succeeds(self):
        counter = self.root / "count.txt"
        task = self.counting_task("flaky", counter, 2,
                                  retryable=True, idempotent=True, max_attempts=3)
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [StageSpec("test", [task])])
        result = self.scheduler().run(spec)
        self.assertEqual(result.status, "completed")
        task_result = result.stages[0].tasks["flaky"]
        self.assertEqual(task_result.status, "succeeded")
        self.assertEqual(task_result.attempts, 3)
        self.assertEqual(task_result.exit_codes, [1, 1, 0])


class TestTimeoutAndAllowlist(SchedulerTestBase):
    def test_timeout_cancels_long_task(self):
        task = TaskSpec(
            "slow",
            [PY, str(HELPERS / "sleep.py"), "30", str(self.marker), "slow-done"],
            timeout_s=0.5,
        )
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [StageSpec("test", [task])])
        result = self.scheduler().run(spec)
        self.assertEqual(result.status, "failed")
        task_result = result.stages[0].tasks["slow"]
        self.assertEqual(task_result.status, "timed_out")
        # The marker is written only after the sleep completes; the
        # process was killed, so it can never appear.
        self.assertEqual(self.marker_lines(), [])

    def test_allowlist_refuses_non_listed_command(self):
        task = TaskSpec("sneaky", ["/bin/echo", "hi"])
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [StageSpec("test", [task])])
        result = self.scheduler().run(spec)
        self.assertEqual(result.status, "failed")
        task_result = result.stages[0].tasks["sneaky"]
        self.assertEqual(task_result.attempts, 0)  # never executed
        self.assertIn("not on the allowlist", task_result.error)


class TestFailurePropagation(SchedulerTestBase):
    def test_dependent_skipped_independent_still_runs(self):
        failing = TaskSpec("a", [PY, str(HELPERS / "fail.py"), "1"])
        dependent = self.marker_task("b", depends_on=("a",))
        independent = self.marker_task("c")
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("test", [failing, dependent, independent]),
        ])
        result = self.scheduler().run(spec)
        self.assertEqual(result.status, "failed")
        tasks = result.stages[0].tasks
        self.assertEqual(tasks["a"].status, "failed")
        self.assertEqual(tasks["b"].status, "skipped")
        self.assertEqual(tasks["b"].attempts, 0)
        self.assertEqual(tasks["c"].status, "succeeded")
        self.assertEqual(self.marker_lines(), ["c"])


class TestIdempotentRunIds(SchedulerTestBase):
    def spec(self):
        return RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("test", [self.marker_task("a")]),
        ])

    def test_duplicate_run_id_does_not_reexecute(self):
        scheduler = self.scheduler()
        first = scheduler.run(self.spec())
        self.assertFalse(first.duplicate)
        second = scheduler.run(self.spec())
        self.assertTrue(second.duplicate)
        self.assertIs(first, second)
        self.assertEqual(self.marker_lines(), ["a"])  # executed exactly once

    def test_run_id_reuse_with_different_spec_refused(self):
        scheduler = self.scheduler()
        scheduler.run(self.spec())
        other = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("test", [self.marker_task("different")]),
        ])
        with self.assertRaises(RunIdConflictError):
            scheduler.run(other)
        self.assertEqual(self.marker_lines(), ["a"])


class TestCycleClose(SchedulerTestBase):
    def test_close_emits_next_intake_package(self):
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [
            StageSpec("test", [self.marker_task("a")]),
        ], carry_findings=("FND-20261112-002",))
        result = self.scheduler().run(spec)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.next_cycle_id, "bibleapp-2026-11-12-002")
        cycles = [r for r in self.cycle_records() if r["cycle_id"] == "bibleapp-2026-11-12-002"]
        self.assertEqual(len(cycles), 1)
        nxt = cycles[0]
        self.assertEqual(nxt["state"], "INTAKE")
        self.assertEqual(nxt["open_findings"], ["FND-20261112-001", "FND-20261112-002"])
        self.assertEqual(nxt["project_id"], "bibleapp")
        self.assertEqual(validate.check(nxt, "cycle"), [])
        closing = [r for r in self.records()
                   if "intake package emitted" in r.get("summary", "")]
        self.assertEqual(len(closing), 1)
        self.assertTrue(self.store.verify().ok)

    def test_failed_run_emits_no_next_cycle(self):
        failing = TaskSpec("a", [PY, str(HELPERS / "fail.py"), "1"])
        spec = RunSpec("run-1", "bibleapp-2026-11-12-001", [StageSpec("test", [failing])])
        result = self.scheduler().run(spec)
        self.assertEqual(result.status, "failed")
        self.assertIsNone(result.next_cycle_id)
        self.assertEqual(self.cycle_records(), [])


if __name__ == "__main__":
    unittest.main()
