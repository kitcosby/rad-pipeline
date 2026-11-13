"""Deterministic probes for project adapters (WP4).

The scheduler's evidence for a task attempt carries the command, the
verdict and an output hash — but not the captured *values* a baseline
report needs (WP3 open question Q8: raw output is not persisted).
Adapter probes therefore run as scheduler tasks through this CLI: each
probe performs its observation, writes a machine-readable JSON result
to a file in the run's work directory, and exits 0/1 by whether the
probe itself could be performed. After the run, the adapter reads the
result files and appends evidence records carrying the exact values.

Three probes:

- ``git-baseline`` — read-only git identity of a repository, executed
  through the WP3 executor with an allowlist of exactly ``{"git"}``
  and a fixed command set (rev-parse / status / tag / log). Nothing
  that can mutate a repository is ever invoked.
- ``http-identity`` — one HTTP endpoint check with the WP2A failure
  taxonomy. A 2xx alone never counts as success: the expected status,
  content markers and (when declared) JSON keys are all asserted, and
  every failure is classified (transport / tls / timeout / http /
  auth / rate_limit / server / protocol / schema / semantic).
- ``inventory`` — requirements/architecture artifact enumeration of a
  project tree: README files, a repository description, package
  descriptions, docs and CEG files, each with a SHA-256 content hash
  (CONTRACTS.md artifact records; README and descriptions are
  acceptance artifacts per IMPLEMENTATION-PLAN WP4).

Exit codes: git-baseline exits 0 iff every git command succeeded;
inventory exits 0 iff the root exists and enumeration completed;
http-identity exits 0 whenever the probe ran and produced a classified
result — a failed endpoint is a *finding for the report*, not a probe
malfunction, so it must not stop the pipe before the report exists.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..executor import Executor
from ..util import now_rfc3339

# The only git subcommands a baseline probe may ever run (read-only).
GIT_COMMANDS = ("rev-parse", "status", "tag", "log")

BODY_EXCERPT_CAP = 1000


# ---------------------------------------------------------------- git

def git_baseline(repo: str) -> dict[str, Any]:
    """Capture branch, HEAD commit, tags and working-tree state."""
    executor = Executor({"git"})
    commands: list[dict[str, Any]] = []

    def git(*args: str) -> tuple[int | None, str]:
        argv = ["git", "-C", repo, *args]
        assert args[0] in GIT_COMMANDS, f"git subcommand {args[0]!r} is not read-only"
        outcome = executor.run(argv, timeout_s=30.0)
        commands.append({"argv": argv, "exit_code": outcome.exit_code})
        return outcome.exit_code, outcome.stdout

    result: dict[str, Any] = {
        "probe": "git-baseline",
        "repo": repo,
        "captured_at": now_rfc3339(),
        "commands": commands,
    }
    code, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    branch = branch.strip()
    if code != 0:
        result.update(ok=False, error=f"git rev-parse failed (exit {code}); "
                                      "not a git repository or no HEAD")
        return result
    code, commit = git("rev-parse", "HEAD")
    commit = commit.strip()
    if code != 0:
        result.update(ok=False, error=f"git rev-parse HEAD failed (exit {code})")
        return result
    code, tag_text = git("tag", "--list")
    if code != 0:
        result.update(ok=False, error=f"git tag --list failed (exit {code})")
        return result
    code, porcelain = git("status", "--porcelain")
    if code != 0:
        result.update(ok=False, error=f"git status failed (exit {code})")
        return result
    tags = sorted(line for line in tag_text.splitlines() if line.strip())
    dirty = [line for line in porcelain.splitlines() if line.strip()]
    result.update(
        ok=True,
        branch=branch,
        commit=commit,
        tags=tags,
        tag_count=len(tags),
        dirty_entries=dirty,
        dirty_count=len(dirty),
        is_clean=len(dirty) == 0,
        error=None,
    )
    return result


# ---------------------------------------------------------------- http

def _classify_url_error(exc: urllib.error.URLError) -> str:
    reason = exc.reason
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "timeout"
    return "transport"


def http_probe(endpoint: dict[str, Any]) -> dict[str, Any]:
    """Probe one HTTP endpoint; classify per the WP2A taxonomy."""
    service = endpoint.get("service", "unnamed")
    url = endpoint["url"]
    method = endpoint.get("method", "GET")
    timeout_s = float(endpoint.get("timeout_s", 10.0))
    expect = endpoint.get("expect") or {}
    expected_status = int(expect.get("status", 200))
    markers = list(expect.get("markers") or [])
    json_keys = list(expect.get("json_keys") or [])

    result: dict[str, Any] = {
        "probe": "http-identity",
        "service": service,
        "url": url,
        "method": method,
        "environment": endpoint.get("environment", ""),
        "captured_at": now_rfc3339(),
        "status": None,
        "content_type": None,
        "response_bytes": 0,
        "response_sha256": None,
        "duration_ms": None,
        "transport_outcome": "ok",
        "parse_verdict": "not-applicable",
        "assertions": [],
        "body_excerpt": "",
        "error": None,
        "classification": None,
        "passed": False,
    }

    request = urllib.request.Request(url, method=method)
    status: int | None = None
    headers: Any = None
    body = b""
    failure: str | None = None
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = response.status
            headers = response.headers
            body = response.read()
    except urllib.error.HTTPError as exc:
        # An HTTP error status is still a response: classify by status.
        status = exc.code
        headers = exc.headers
        try:
            body = exc.read() or b""
        except Exception:
            body = b""
    except urllib.error.URLError as exc:
        failure = _classify_url_error(exc)
        result["error"] = f"{type(exc).__name__}: {exc.reason}"
    except (socket.timeout, TimeoutError) as exc:
        failure = "timeout"
        result["error"] = f"{type(exc).__name__}: {exc}"
    except ssl.SSLError as exc:
        failure = "tls"
        result["error"] = f"{type(exc).__name__}: {exc}"
    except ConnectionError as exc:
        failure = "transport"
        result["error"] = f"{type(exc).__name__}: {exc}"
    except http.client.HTTPException as exc:
        failure = "protocol"
        result["error"] = f"{type(exc).__name__}: {exc}"
    except (OSError, ValueError) as exc:
        failure = "transport" if isinstance(exc, OSError) else "protocol"
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["duration_ms"] = round((time.monotonic() - started) * 1000.0, 3)

    if failure is not None:
        result["transport_outcome"] = failure
        result["classification"] = failure
        return result

    assert status is not None  # a response was received
    result["status"] = status
    content_type = headers.get_content_type() if headers is not None else None
    result["content_type"] = content_type
    result["response_bytes"] = len(body)
    result["response_sha256"] = hashlib.sha256(body).hexdigest()
    result["body_excerpt"] = body[:BODY_EXCERPT_CAP].decode("utf-8", errors="replace")

    assertions: list[dict[str, Any]] = result["assertions"]
    assertions.append({
        "name": f"status == {expected_status}",
        "passed": status == expected_status,
        "expected": expected_status,
        "actual": status,
    })
    if status != expected_status:
        if status in (401, 403):
            result["classification"] = "auth"
        elif status == 429:
            result["classification"] = "rate_limit"
        elif 500 <= status <= 599:
            result["classification"] = "server"
        else:
            result["classification"] = "http"
        return result

    classification = "ok"
    if json_keys:
        try:
            parsed = json.loads(body.decode("utf-8"))
            result["parse_verdict"] = "json-ok"
        except (ValueError, UnicodeDecodeError):
            parsed = None
            result["parse_verdict"] = "invalid-json"
            classification = "schema"
        if parsed is not None:
            for key in json_keys:
                present = isinstance(parsed, dict) and key in parsed
                assertions.append({
                    "name": f"json key {key!r} present",
                    "passed": present,
                    "expected": key,
                    "actual": parsed.get(key) if isinstance(parsed, dict) else None,
                })
                if not present:
                    classification = "schema"
    text = body.decode("utf-8", errors="replace")
    for marker in markers:
        present = marker in text
        assertions.append({
            "name": f"content marker {marker!r}",
            "passed": present,
            "expected": marker,
            "actual": "present" if present else "absent",
        })
        if not present and classification == "ok":
            classification = "semantic"
    result["classification"] = classification
    result["passed"] = classification == "ok"
    return result


# ---------------------------------------------------------------- inventory

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
_GIT_DEFAULT_DESCRIPTION = (
    "Unnamed repository; edit this file 'description' to name the repository."
)


def _artifact(project_id: str, root: Path, path: Path, type_: str,
              valid_from: str) -> dict[str, Any]:
    rel = path.relative_to(root).as_posix()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "artifact_id": f"{project_id}:{rel}",
        "project_id": project_id,
        "type": type_,
        "canonical_location": rel,
        "revision": digest,
        "content_hash": digest,
        "authority": "observed",
        "valid_from": valid_from,
    }


def inventory_artifacts(
    root: str,
    project_id: str,
    *,
    exclude: list[str] | tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Enumerate the requirements/architecture artifact set of a tree.

    Adapter classification rules (CONTRACTS.md artifact types):
    README* files are ``readme``; a root DESCRIPTION/description file
    and a non-default .git/description are ``repository_description``;
    package.json with a description is ``package_description`` (without
    one it is ``config``); Markdown under docs/ is ``architecture``;
    *.ceg files are ``ceg``. Everything else is not inventoried.
    """
    root_path = Path(root)
    valid_from = now_rfc3339()
    artifacts: list[dict[str, Any]] = []
    excluded = tuple(exclude)

    def skipped(rel: str) -> bool:
        return any(rel == ex or rel.startswith(ex.rstrip("/") + "/") for ex in excluded)

    for path in sorted(root_path.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root_path).as_posix()
        parts = rel.split("/")
        if any(part in _SKIP_DIRS for part in parts[:-1]) or skipped(rel):
            continue
        name = path.name
        if name.upper().startswith("README"):
            artifacts.append(_artifact(project_id, root_path, path, "readme", valid_from))
        elif rel in ("DESCRIPTION", "description"):
            artifacts.append(
                _artifact(project_id, root_path, path, "repository_description", valid_from)
            )
        elif name == "package.json":
            type_ = "config"
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("description"):
                    type_ = "package_description"
            except (ValueError, OSError):
                pass
            artifacts.append(_artifact(project_id, root_path, path, type_, valid_from))
        elif parts[0] == "docs" and path.suffix == ".md":
            artifacts.append(
                _artifact(project_id, root_path, path, "architecture", valid_from)
            )
        elif path.suffix == ".ceg":
            artifacts.append(_artifact(project_id, root_path, path, "ceg", valid_from))

    description = root_path / ".git" / "description"
    if description.is_file():
        try:
            text = description.read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text and text != _GIT_DEFAULT_DESCRIPTION:
            artifacts.append({
                "artifact_id": f"{project_id}:.git/description",
                "project_id": project_id,
                "type": "repository_description",
                "canonical_location": ".git/description",
                "revision": hashlib.sha256(
                    description.read_bytes()
                ).hexdigest(),
                "content_hash": hashlib.sha256(
                    description.read_bytes()
                ).hexdigest(),
                "authority": "observed",
                "valid_from": valid_from,
            })
    artifacts.sort(key=lambda a: a["canonical_location"])
    return artifacts


# ---------------------------------------------------------------- CLI

def _write_result(path: str, payload: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radpipe.adapters.probe")
    sub = parser.add_subparsers(dest="command", required=True)

    p_git = sub.add_parser("git-baseline")
    p_git.add_argument("--repo", required=True)
    p_git.add_argument("--out", required=True)

    p_http = sub.add_parser("http-identity")
    p_http.add_argument("--endpoint-json", required=True)
    p_http.add_argument("--out", required=True)

    p_inv = sub.add_parser("inventory")
    p_inv.add_argument("--root", required=True)
    p_inv.add_argument("--project-id", required=True)
    p_inv.add_argument("--exclude", action="append", default=[])
    p_inv.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.command == "git-baseline":
        result = git_baseline(args.repo)
        _write_result(args.out, result)
        return 0 if result["ok"] else 1
    if args.command == "http-identity":
        endpoint = json.loads(args.endpoint_json)
        _write_result(args.out, http_probe(endpoint))
        return 0  # a classified failure is a result, not a probe error
    if args.command == "inventory":
        if not Path(args.root).is_dir():
            _write_result(args.out, {
                "probe": "inventory", "root": args.root, "ok": False,
                "error": f"inventory root {args.root!r} is not a directory",
                "artifacts": [],
            })
            return 1
        artifacts = inventory_artifacts(
            args.root, args.project_id, exclude=tuple(args.exclude)
        )
        _write_result(args.out, {
            "probe": "inventory", "root": args.root, "ok": True,
            "error": None, "artifacts": artifacts,
        })
        return 0
    return 2  # unreachable: argparse enforces the subcommand


if __name__ == "__main__":
    sys.exit(main())
