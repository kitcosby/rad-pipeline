"""Shared fixtures for the WP4 BibleApp adapter tests.

Builds a real temp git repository (an independent oracle is computed
with subprocess git, never through the adapter) and adapter configs
rooted in temp directories. Fully offline.
"""

import json
import socket
import subprocess
import sys
from pathlib import Path

PY = sys.executable
HELPERS = Path(__file__).resolve().parent / "helpers"


def git(repo: Path, *args: str) -> str:
    """Oracle git: run git directly and return raw stdout."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    ).stdout


def make_repo(root: Path) -> dict:
    """Create a git repo fixture; return its path and oracle values."""
    repo = root / "project"
    (repo / "docs").mkdir(parents=True)
    (repo / "suites").mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
    git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "Adapter Fixture")
    (repo / "README.md").write_text("# Fixture BibleApp\n\nFixture readme.\n")
    (repo / "DESCRIPTION").write_text("Fixture BibleApp staging tree\n")
    (repo / "docs" / "guide.md").write_text("# Architecture guide\n")
    (repo / "package.json").write_text(json.dumps(
        {"name": "fixture-bibleapp", "description": "Fixture project description"}
    ))
    (repo / "suites" / "sample.ceg").write_text("graph fixture\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "fixture baseline")
    git(repo, "tag", "v0.1.0")
    return {
        "repo": repo,
        "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "commit": git(repo, "rev-parse", "HEAD").strip(),
        "tags": sorted(
            line for line in git(repo, "tag", "--list").splitlines() if line.strip()
        ),
    }


def make_config(root: Path, repo: Path, **overrides) -> dict:
    """A complete adapter config rooted under ``root`` (absolute paths)."""
    config = {
        "project_id": "bibleapp",
        "repo_path": str(repo),
        "evidence_path": str(root / "run" / "evidence.jsonl"),
        "work_dir": str(root / "run" / "work"),
        "python_executable": PY,
        "allowlist": [PY, "git"],
        "policy_profile": "bibleapp-nonprod-test",
        "parallel_bound": 4,
        "endpoints": [],
        "batteries": [],
        "inventory": {"root": str(repo)},
    }
    config.update(overrides)
    return config


def unused_port() -> int:
    """A port that is free right now (connection attempts are refused)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
