"""BibleApp project adapter (WP4) — first project adapter.

Implements the CONTRACTS.md project-adapter boundary for the BibleApp
estate, non-production first (IMPLEMENTATION-PLAN WP4):

- ``baseline`` stage: read-only git identity probes of the project
  repository (branch, HEAD commit, tags, working-tree state), executed
  through the WP3 executor allowlist (see adapters/probe.py).
- ``identity`` stage: staging build/runtime identity probes over HTTP
  with the WP2A failure taxonomy — a 2xx alone never counts as
  success; expected status, content markers and JSON keys are asserted.
- ``inventory`` stage: requirements/architecture inventory — the
  project's README, repository/package descriptions and docs set as
  hashed artifact records (README and descriptions are acceptance
  artifacts).
- ``qa`` stage: the project's EXISTING QA batteries, run through their
  existing interfaces as a non-production smoke/regression plan
  (config-declared argv, still through the allowlist executor).
- ``ceg-generation`` stage (only when config requests it): guarded by
  the WP3 ``CegGenerationGate``. The cycle carries the
  ``ceg_paradigm_cleanup`` flag from config; absent any config value it
  is not DONE, so generation is blocked — the standing gate, enforced
  by policy rather than mentioned in a report.

Every probe result lands in the WP2 evidence store with its content
hash, and the cycle emits a baseline report (dict + Markdown) whose
values are the exact captured values, each section naming the evidence
record it traces to. Nothing here hard-codes Lampy paths: every
location, endpoint, command and flag comes from the adapter config
(see bibleapp.example.json).
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..evidence import EvidenceStore, content_hash
from ..executor import Executor
from ..policy import CegGenerationGate, GateRegistry
from ..scheduler import RunResult, RunSpec, Scheduler, StageSpec, TaskSpec
from ..util import new_evidence_id, now_rfc3339
from . import probe as _probe

_PACKAGE_PARENT = Path(__file__).resolve().parents[2]


@dataclass
class AdapterRun:
    """The outcome of one adapter baseline cycle."""

    cycle: dict[str, Any]
    run_result: RunResult
    report: dict[str, Any]
    report_markdown: str


def _slug(text: str, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", str(text)).strip("-")
    return slug or fallback


class BibleAppAdapter:
    """Supplies the BibleApp baseline cycle to the RAD core."""

    def __init__(self, config: dict[str, Any], *, base_dir: str | Path | None = None):
        self.config = dict(config)
        self.base_dir = Path(base_dir) if base_dir is not None else Path.cwd()
        self.project_id = str(self.config.get("project_id", "bibleapp"))
        self.repo_path = self._resolve(self.config.get("repo_path", "."))
        self.evidence_path = self._resolve(
            self.config.get("evidence_path", "evidence/evidence.jsonl")
        )
        self.work_dir = self._resolve(self.config.get("work_dir", "work"))
        self.actor = str(self.config.get("actor", "radpipe-bibleapp-adapter"))
        self.python_executable = str(
            self.config.get("python_executable", sys.executable)
        )
        allowlist = self.config.get("allowlist")
        if not allowlist:
            raise ValueError(
                "adapter config must declare an allowlist of executable programs"
            )
        self.allowlist = [str(item) for item in allowlist]
        if self.python_executable not in self.allowlist:
            raise ValueError(
                "adapter config allowlist must include the python_executable "
                f"{self.python_executable!r} used for probe tasks"
            )

    # -- construction ---------------------------------------------------

    @classmethod
    def from_config_file(cls, path: str | Path) -> "BibleAppAdapter":
        config_path = Path(path)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return cls(config, base_dir=config_path.resolve().parent)

    def _resolve(self, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else (self.base_dir / path)

    # -- adapter contract surface ----------------------------------------

    def describe_project(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "repository": str(self.repo_path),
            "targets": "non-production (staging) only",
            "endpoints": [
                ep.get("service", "unnamed") for ep in self.config.get("endpoints", [])
            ],
            "batteries": [
                b.get("name", "unnamed") for b in self.config.get("batteries", [])
            ],
            "ceg_generation_requested": bool(
                (self.config.get("ceg_generation") or {}).get("requested", False)
            ),
            "ceg_paradigm_cleanup": self.config.get("ceg_paradigm_cleanup"),
        }

    def inventory_artifacts(self) -> list[dict[str, Any]]:
        """The artifact inventory, computed in-process (same code the
        inventory probe task runs on the pipe)."""
        inventory_cfg = self.config.get("inventory") or {}
        root = inventory_cfg.get("root") or str(self.repo_path)
        return _probe.inventory_artifacts(
            str(self._resolve(root)),
            self.project_id,
            exclude=tuple(inventory_cfg.get("exclude") or ()),
        )

    # -- cycle assembly ---------------------------------------------------

    def _probe_task(self, task_id: str, probe_args: list[str]) -> TaskSpec:
        pythonpath = str(_PACKAGE_PARENT)
        existing = os.environ.get("PYTHONPATH")
        if existing:
            pythonpath = pythonpath + os.pathsep + existing
        return TaskSpec(
            task_id=task_id,
            argv=[self.python_executable, "-m", "radpipe.adapters.probe", *probe_args],
            timeout_s=120.0,
            env={"PYTHONPATH": pythonpath},
        )

    def build_cycle(self, cycle_id: str) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "project_id": self.project_id,
            "cycle_id": cycle_id,
            "created_at": now_rfc3339(),
            "intent": str(
                self.config.get(
                    "intent",
                    "BibleApp non-production baseline: git identity, staging "
                    "identity probes, artifact inventory, existing QA batteries.",
                )
            ),
            "baseline": {"status": "pending"},
            "state": "INTAKE",
            "policy_profile": str(
                self.config.get("policy_profile", "bibleapp-nonprod")
            ),
            "artifact_inventory_ref": str(self.work_dir / "inventory.json"),
            "approval_refs": [],
            "open_findings": [],
        }

    def build_run_spec(self, cycle_id: str, run_id: str) -> RunSpec:
        work = self.work_dir
        stages: list[StageSpec] = []

        stages.append(StageSpec(
            stage_id="baseline",
            kind="build",
            inputs=(f"repo:{self.repo_path}",),
            tasks=[self._probe_task("git-baseline", [
                "git-baseline", "--repo", str(self.repo_path),
                "--out", str(work / "git-baseline.json"),
            ])],
        ))

        identity_tasks = []
        for index, endpoint in enumerate(self.config.get("endpoints", [])):
            service = _slug(endpoint.get("service", "endpoint"), "endpoint")
            identity_tasks.append(self._probe_task(
                f"identity-{index}-{service}",
                ["http-identity",
                 "--endpoint-json", json.dumps(endpoint),
                 "--out", str(work / f"identity-{index}-{service}.json")],
            ))
        stages.append(StageSpec(
            stage_id="identity", kind="test", tasks=identity_tasks,
            inputs=tuple(
                f"endpoint:{ep.get('service', 'unnamed')}"
                for ep in self.config.get("endpoints", [])
            ),
        ))

        inventory_cfg = self.config.get("inventory") or {}
        inventory_root = self._resolve(inventory_cfg.get("root") or str(self.repo_path))
        inventory_args = [
            "inventory", "--root", str(inventory_root),
            "--project-id", self.project_id,
            "--out", str(work / "inventory.json"),
        ]
        for excluded in inventory_cfg.get("exclude") or ():
            inventory_args += ["--exclude", str(excluded)]
        stages.append(StageSpec(
            stage_id="inventory", kind="audit",
            tasks=[self._probe_task("artifact-inventory", inventory_args)],
            inputs=(f"root:{inventory_root}",),
        ))

        qa_tasks = []
        for index, battery in enumerate(self.config.get("batteries", [])):
            name = _slug(battery.get("name", "battery"), "battery")
            cwd = battery.get("cwd")
            qa_tasks.append(TaskSpec(
                task_id=f"qa-{index}-{name}",
                argv=[str(a) for a in battery["argv"]],
                timeout_s=float(battery.get("timeout_s", 300.0)),
                retryable=bool(battery.get("retryable", False)),
                idempotent=bool(battery.get("idempotent", False)),
                max_attempts=int(battery.get("max_attempts", 1)),
                cwd=str(self._resolve(cwd)) if cwd else None,
            ))
        stages.append(StageSpec(stage_id="qa", kind="test", tasks=qa_tasks))

        generation = self.config.get("ceg_generation") or {}
        if generation.get("requested", False):
            cwd = generation.get("cwd")
            stages.append(StageSpec(
                stage_id="ceg-generation",
                kind="build",
                gates=("ceg-generation",),
                action="ceg_generation",
                tasks=[TaskSpec(
                    task_id="ceg-generation",
                    argv=[str(a) for a in generation["argv"]],
                    timeout_s=float(generation.get("timeout_s", 300.0)),
                    cwd=str(self._resolve(cwd)) if cwd else None,
                )],
            ))

        flags: dict[str, Any] = {}
        if "ceg_paradigm_cleanup" in self.config:
            flags["ceg_paradigm_cleanup"] = self.config["ceg_paradigm_cleanup"]
        return RunSpec(
            run_id=run_id,
            cycle_id=cycle_id,
            stages=stages,
            flags=flags,
            next_cycle_id=self.config.get("next_cycle_id"),
        )

    # -- execution ---------------------------------------------------------

    def run_cycle(
        self,
        *,
        cycle_id: str | None = None,
        run_id: str | None = None,
    ) -> AdapterRun:
        cycle_id = cycle_id or f"{self.project_id}-{uuid.uuid4().hex[:8]}"
        run_id = run_id or f"run-{cycle_id}"
        cycle = self.build_cycle(cycle_id)
        spec = self.build_run_spec(cycle_id, run_id)

        self.work_dir.mkdir(parents=True, exist_ok=True)
        store = EvidenceStore(self.evidence_path)
        executor = Executor(self.allowlist)
        registry = GateRegistry().register(CegGenerationGate())
        scheduler = Scheduler(
            store,
            cycle,
            executor,
            registry,
            parallel_bound=int(self.config.get("parallel_bound", 4)),
            actor=self.actor,
        )
        run_result = scheduler.run(spec)
        report = self._build_report(cycle, run_result, store)
        return AdapterRun(
            cycle=cycle,
            run_result=run_result,
            report=report,
            report_markdown=render_report_markdown(report),
        )

    # -- post-run evidence + report -----------------------------------------

    def _append_evidence(self, store: EvidenceStore, record: dict[str, Any]) -> str:
        envelope = store.append(record)
        return envelope["record"]["evidence_id"]

    def _base_record(
        self, cycle: dict[str, Any], run_id: str, stage_id: str,
        evidence_class: str, source: str, summary: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "evidence_id": new_evidence_id("EVD-ADP"),
            "cycle_id": cycle["cycle_id"],
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

    def _build_report(
        self, cycle: dict[str, Any], run_result: RunResult, store: EvidenceStore
    ) -> dict[str, Any]:
        run_id = run_result.run_id
        report: dict[str, Any] = {
            "project_id": self.project_id,
            "cycle_id": cycle["cycle_id"],
            "run_id": run_id,
            "generated_at": now_rfc3339(),
            "run_status": run_result.status,
            "baseline": {"status": "pending"},
            "git": None,
            "identity": [],
            "inventory": {"count": 0, "artifacts": [], "evidence_id": None},
            "qa": [],
            "ceg_generation": {
                "requested": bool(
                    (self.config.get("ceg_generation") or {}).get("requested", False)
                ),
                "cleanup_flag": self.config.get("ceg_paradigm_cleanup"),
                "gate": None,
                "task_status": None,
            },
            "evidence": {"store": str(self.evidence_path), "records": 0,
                         "chain_ok": False},
        }

        # Git baseline: exact values from the probe result, hashed into
        # an evidence record; the report quotes the probe, never a
        # paraphrase of it.
        git_file = self.work_dir / "git-baseline.json"
        if git_file.is_file():
            git = json.loads(git_file.read_text(encoding="utf-8"))
            if git.get("ok"):
                dirty = git["dirty_entries"]
                tree = (
                    "working tree clean (0 uncommitted entries)"
                    if git["is_clean"]
                    else "working tree DIRTY ("
                    f"{git['dirty_count']} uncommitted entries: "
                    + ", ".join(repr(entry) for entry in dirty)
                    + ")"
                )
                summary = (
                    f"Git baseline for {git['repo']}: branch {git['branch']!r}; "
                    f"HEAD commit {git['commit']}; {git['tag_count']} tag(s)"
                    + (f": {', '.join(git['tags'])}" if git["tags"] else "")
                    + f"; {tree}."
                )
                record = self._base_record(
                    cycle, run_id, "baseline", "VERIFIED",
                    "probe://git-baseline", summary,
                )
                record["sha256"] = content_hash(git)
                evidence_id = self._append_evidence(store, record)
                report["git"] = {
                    "repo": git["repo"],
                    "branch": git["branch"],
                    "commit": git["commit"],
                    "tags": git["tags"],
                    "tag_count": git["tag_count"],
                    "dirty_entries": dirty,
                    "dirty_count": git["dirty_count"],
                    "is_clean": git["is_clean"],
                    "evidence_id": evidence_id,
                }
                report["baseline"] = {
                    "status": "recorded",
                    "repository": git["repo"],
                    "branch": git["branch"],
                    "commit": git["commit"],
                }
            else:
                record = self._base_record(
                    cycle, run_id, "baseline", "VERIFIED",
                    "probe://git-baseline",
                    f"Git baseline probe FAILED for {git['repo']}: {git.get('error')}",
                )
                record["sha256"] = content_hash(git)
                evidence_id = self._append_evidence(store, record)
                report["git"] = {"repo": git["repo"], "ok": False,
                                 "error": git.get("error"),
                                 "evidence_id": evidence_id}

        # Identity probes: one DEMONSTRATED evidence record per endpoint,
        # with the WP2 API-evidence block filled from the probe result.
        for index, endpoint in enumerate(self.config.get("endpoints", [])):
            service = _slug(endpoint.get("service", "endpoint"), "endpoint")
            result_file = self.work_dir / f"identity-{index}-{service}.json"
            if not result_file.is_file():
                report["identity"].append({
                    "service": endpoint.get("service", "unnamed"),
                    "url": endpoint["url"], "classification": "not-run",
                    "evidence_id": None,
                })
                continue
            probe_result = json.loads(result_file.read_text(encoding="utf-8"))
            assertions = probe_result["assertions"]
            passed_count = sum(1 for a in assertions if a["passed"])
            if probe_result["status"] is not None:
                summary = (
                    f"Identity probe {probe_result['method']} {probe_result['url']} "
                    f"-> HTTP {probe_result['status']} in "
                    f"{probe_result['duration_ms']} ms; classification "
                    f"{probe_result['classification']}; content-type "
                    f"{probe_result['content_type']}; {probe_result['response_bytes']} "
                    f"bytes; assertions {passed_count}/{len(assertions)} passed."
                )
            else:
                summary = (
                    f"Identity probe {probe_result['method']} {probe_result['url']} "
                    f"failed before any response: classification "
                    f"{probe_result['classification']} ({probe_result['error']})."
                )
            record = self._base_record(
                cycle, run_id, "identity", "DEMONSTRATED",
                f"http-probe://{probe_result['service']}", summary,
            )
            api: dict[str, Any] = {
                "service": probe_result["service"],
                "method": probe_result["method"],
                "path": probe_result["url"],
                "transport_outcome": probe_result["transport_outcome"],
                "duration_ms": probe_result["duration_ms"],
                "parse_verdict": probe_result["parse_verdict"],
                "assertion_results": assertions,
                "retry_safe": probe_result["method"] in ("GET", "HEAD"),
                "response_bytes": probe_result["response_bytes"],
            }
            if probe_result["status"] is not None:
                api["status"] = probe_result["status"]
            if probe_result["content_type"] is not None:
                api["content_type"] = probe_result["content_type"]
            if probe_result["response_sha256"] is not None:
                api["response_sha256"] = probe_result["response_sha256"]
            if probe_result["environment"]:
                api["environment"] = probe_result["environment"]
            record["api"] = api
            record["sha256"] = content_hash(probe_result)
            evidence_id = self._append_evidence(store, record)
            report["identity"].append({
                "service": probe_result["service"],
                "url": probe_result["url"],
                "classification": probe_result["classification"],
                "passed": probe_result["passed"],
                "status": probe_result["status"],
                "duration_ms": probe_result["duration_ms"],
                "response_bytes": probe_result["response_bytes"],
                "response_sha256": probe_result["response_sha256"],
                "assertions_passed": passed_count,
                "assertions_total": len(assertions),
                "evidence_id": evidence_id,
            })

        # Artifact inventory.
        inventory_file = self.work_dir / "inventory.json"
        if inventory_file.is_file():
            payload = json.loads(inventory_file.read_text(encoding="utf-8"))
            artifacts = payload.get("artifacts", [])
            by_type: dict[str, int] = {}
            for artifact in artifacts:
                by_type[artifact["type"]] = by_type.get(artifact["type"], 0) + 1
            breakdown = ", ".join(
                f"{type_}: {count}" for type_, count in sorted(by_type.items())
            ) or "none"
            record = self._base_record(
                cycle, run_id, "inventory", "VERIFIED",
                "probe://artifact-inventory",
                f"Artifact inventory of {payload.get('root')}: "
                f"{len(artifacts)} artifact(s) ({breakdown}).",
            )
            record["sha256"] = content_hash({"artifacts": artifacts})
            record["related_artifact_ids"] = [a["artifact_id"] for a in artifacts]
            evidence_id = self._append_evidence(store, record)
            report["inventory"] = {
                "count": len(artifacts),
                "artifacts": artifacts,
                "evidence_id": evidence_id,
            }

        # QA batteries and the CEG gate, from the scheduler's results —
        # every number here is the TaskResult the scheduler evidenced.
        stage_by_id = {s.stage_id: s for s in run_result.stages}
        qa_stage = stage_by_id.get("qa")
        if qa_stage is not None:
            for task in qa_stage.tasks.values():
                report["qa"].append({
                    "task_id": task.task_id,
                    "status": task.status,
                    "attempts": task.attempts,
                    "exit_codes": task.exit_codes,
                    "evidence_ids": task.evidence_ids,
                })
        generation_stage = stage_by_id.get("ceg-generation")
        if report["ceg_generation"]["requested"]:
            if generation_stage is None:
                report["ceg_generation"]["gate"] = "stage-not-run"
            else:
                for decision in generation_stage.gate_decisions:
                    if decision.gate == "ceg-generation":
                        report["ceg_generation"]["gate"] = {
                            "allowed": decision.allowed,
                            "reason": decision.reason,
                        }
                task = generation_stage.tasks.get("ceg-generation")
                if task is not None:
                    report["ceg_generation"]["task_status"] = task.status

        verify = store.verify()
        report["evidence"] = {
            "store": str(self.evidence_path),
            "records": len(store.records()),
            "chain_ok": verify.ok,
        }
        return report


# ---------------------------------------------------------------- report

def render_report_markdown(report: dict[str, Any]) -> str:
    """Render a baseline report dict as Markdown (exact values only)."""
    lines = [
        f"# BibleApp baseline report — {report['project_id']}",
        "",
        f"- Cycle: {report['cycle_id']}",
        f"- Run: {report['run_id']} (status: {report['run_status']})",
        f"- Generated: {report['generated_at']}",
        "",
        "## Git baseline",
        "",
    ]
    git = report.get("git")
    if git is None:
        lines.append("Not captured (baseline stage did not produce a result).")
    elif git.get("ok") is False:
        lines.append(f"Probe failed for {git['repo']}: {git.get('error')}")
    else:
        lines += [
            f"- Repository: {git['repo']}",
            f"- Branch: {git['branch']}",
            f"- HEAD commit: {git['commit']}",
            f"- Tags ({git['tag_count']}): "
            + (", ".join(git["tags"]) if git["tags"] else "none"),
            f"- Working tree: "
            + ("clean" if git["is_clean"]
               else f"DIRTY — {git['dirty_count']} uncommitted entries: "
                    + ", ".join(git["dirty_entries"])),
            f"- Evidence: {git['evidence_id']}",
        ]
    lines += ["", "## Staging identity probes", ""]
    if not report["identity"]:
        lines.append("No endpoints configured.")
    for probe in report["identity"]:
        lines.append(
            f"- {probe['service']} — {probe['url']}: classification "
            f"{probe['classification']}, HTTP status {probe['status']}, "
            f"{probe['duration_ms']} ms, assertions "
            f"{probe.get('assertions_passed')}/{probe.get('assertions_total')}, "
            f"evidence {probe['evidence_id']}"
        )
    inventory = report["inventory"]
    lines += ["", "## Artifact inventory", "",
              f"{inventory['count']} artifact(s), evidence "
              f"{inventory['evidence_id']}", ""]
    for artifact in inventory["artifacts"]:
        lines.append(
            f"- {artifact['artifact_id']} ({artifact['type']}) "
            f"sha256 {artifact['content_hash']}"
        )
    lines += ["", "## QA batteries", ""]
    if not report["qa"]:
        lines.append("No batteries ran.")
    for task in report["qa"]:
        lines.append(
            f"- {task['task_id']}: {task['status']}, "
            f"{task['attempts']} attempt(s), exit codes {task['exit_codes']}, "
            f"evidence {', '.join(task['evidence_ids']) or 'none'}"
        )
    generation = report["ceg_generation"]
    lines += ["", "## CEG generation", ""]
    if not generation["requested"]:
        lines.append("Not requested in this cycle's config.")
    else:
        gate = generation["gate"]
        if isinstance(gate, dict):
            verdict = "ALLOWED" if gate["allowed"] else "DENIED"
            lines.append(
                f"Gate {verdict}: {gate['reason']} "
                f"(ceg_paradigm_cleanup flag: {generation['cleanup_flag']!r}; "
                f"generation task: {generation['task_status']})"
            )
        else:
            lines.append(f"Gate: {gate} (flag: {generation['cleanup_flag']!r})")
    evidence = report["evidence"]
    lines += ["", "## Evidence", "",
              f"- Store: {evidence['store']}",
              f"- Records: {evidence['records']}",
              f"- Hash chain verifies: {evidence['chain_ok']}",
              ""]
    return "\n".join(lines)
