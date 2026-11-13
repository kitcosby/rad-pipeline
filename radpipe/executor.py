"""Subprocess task executor (WP3) — allowlisted, shell-free, bounded.

Rules (CONTRACTS.md "Execution safety"):

- Commands are structured argv, never shell strings; ``shell=False``
  always.
- ``argv[0]`` must appear verbatim in the executor's allowlist, or the
  command is refused before anything runs (CommandNotAllowedError).
- Each run has a timeout; on expiry the whole process group is killed
  (tasks start in their own session) and the outcome is reported as
  timed out — a timeout is never a pass.
- stdout/stderr are captured and capped at ``output_cap`` bytes each;
  truncation is flagged on the outcome, not silent.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass

DEFAULT_OUTPUT_CAP = 64 * 1024


class CommandNotAllowedError(Exception):
    """Raised when argv[0] is not on the executor's allowlist."""

    def __init__(self, program: str):
        self.program = program
        super().__init__(
            f"command {program!r} is not on the allowlist; refused before execution"
        )


@dataclass
class TaskOutcome:
    exit_code: int | None  # None when the process never exited normally
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    error: str | None = None  # spawn failure etc.; exit_code stays None

    @property
    def succeeded(self) -> bool:
        return not self.timed_out and self.error is None and self.exit_code == 0


class Executor:
    """Runs allowlisted argv commands with timeout and output capture."""

    def __init__(
        self,
        allowlist: set[str] | frozenset[str] | list[str],
        *,
        output_cap: int = DEFAULT_OUTPUT_CAP,
    ):
        self.allowlist = frozenset(allowlist)
        self.output_cap = output_cap

    def check_allowed(self, argv: list[str]) -> None:
        if not argv:
            raise CommandNotAllowedError("<empty argv>")
        if argv[0] not in self.allowlist:
            raise CommandNotAllowedError(argv[0])

    def run(
        self,
        argv: list[str],
        *,
        timeout_s: float,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> TaskOutcome:
        self.check_allowed(argv)
        full_env = dict(os.environ)
        if env:
            full_env.update(env)
        try:
            proc = subprocess.Popen(
                list(argv),
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=full_env,
                start_new_session=True,  # own process group: timeout kills the tree
            )
        except OSError as exc:
            return TaskOutcome(exit_code=None, error=f"{type(exc).__name__}: {exc}")
        timed_out = False
        try:
            raw_out, raw_err = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            raw_out, raw_err = proc.communicate()
        truncated = len(raw_out) > self.output_cap or len(raw_err) > self.output_cap
        return TaskOutcome(
            exit_code=None if timed_out else proc.returncode,
            timed_out=timed_out,
            stdout=raw_out[: self.output_cap].decode("utf-8", errors="replace"),
            stderr=raw_err[: self.output_cap].decode("utf-8", errors="replace"),
            truncated=truncated,
        )
