"""Append-only, hash-chained evidence store (WP2).

On-disk format: one JSON object per line (JSONL). Each line is an
envelope::

    {"seq": <int>, "prev_hash": <hex64>, "hash": <hex64>, "record": {...}}

``hash`` is the SHA-256 of ``prev_hash`` concatenated with the canonical
JSON encoding of ``record`` (keys sorted, no insignificant whitespace,
UTF-8). The first record chains to GENESIS_HASH (64 zero hex digits).
Because every record's hash covers the previous record's hash, editing,
deleting or re-ordering any earlier line breaks verification at that
point; appending never rewrites earlier bytes.

Write path: the incoming record is REDACTED first (radpipe.redact), then
VALIDATED against the evidence schema (radpipe.validate); malformed or
incomplete evidence is refused, never persisted. Corrections are new
records whose ``supersedes`` field names the records they replace; prior
records are never mutated.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from . import redact as _redact
from . import validate as _validate

GENESIS_HASH = "0" * 64


def canonical_bytes(obj: Any) -> bytes:
    """Canonical JSON encoding used for hashing."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def chain_hash(prev_hash: str, record: Any) -> str:
    """SHA-256 content hash of ``record`` chained to ``prev_hash``."""
    return hashlib.sha256(prev_hash.encode("ascii") + canonical_bytes(record)).hexdigest()


def content_hash(record: Any) -> str:
    """Plain SHA-256 of the canonical encoding of ``record`` (unchained)."""
    return hashlib.sha256(canonical_bytes(record)).hexdigest()


@dataclass
class VerifyReport:
    ok: bool
    count: int = 0
    errors: list[str] = field(default_factory=list)


class ChainError(Exception):
    """Raised when an existing store file is corrupt and cannot be extended."""


def _iter_lines(path: Path) -> Iterator[tuple[int, str]]:
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if line.strip():
                yield lineno, line


def verify_file(path: str | Path) -> VerifyReport:
    """Verify the whole chain in ``path``; detect any tampering.

    Detects: malformed lines, wrong sequence numbers, broken prev_hash
    linkage, and content-hash mismatches (edited records).
    """
    path = Path(path)
    errors: list[str] = []
    if not path.exists():
        return VerifyReport(ok=True, count=0, errors=[])
    prev_hash = GENESIS_HASH
    expected_seq = 0
    count = 0
    for lineno, line in _iter_lines(path):
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {lineno}: not valid JSON ({exc.msg})")
            break
        if not isinstance(envelope, dict) or not {"seq", "prev_hash", "hash", "record"} <= set(envelope):
            errors.append(f"line {lineno}: envelope missing seq/prev_hash/hash/record")
            break
        if envelope["seq"] != expected_seq:
            errors.append(
                f"line {lineno}: seq is {envelope['seq']!r}, expected {expected_seq} "
                "(record deleted, duplicated or re-ordered)"
            )
            break
        if envelope["prev_hash"] != prev_hash:
            errors.append(
                f"line {lineno}: prev_hash does not match the previous record's hash "
                "(chain break)"
            )
            break
        actual = chain_hash(envelope["prev_hash"], envelope["record"])
        if actual != envelope["hash"]:
            errors.append(
                f"line {lineno}: content hash mismatch (record was modified after writing)"
            )
            break
        prev_hash = envelope["hash"]
        expected_seq += 1
        count += 1
    return VerifyReport(ok=not errors, count=count, errors=errors)


class EvidenceStore:
    """An append-only evidence log backed by one JSONL file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    # -- reading ------------------------------------------------------

    def _tail(self) -> tuple[int, str]:
        """Return (next_seq, last_hash); raise ChainError if the file is corrupt."""
        report = verify_file(self.path)
        if not report.ok:
            raise ChainError(
                f"refusing to extend a corrupt evidence store at {self.path}: "
                + "; ".join(report.errors)
            )
        last_hash = GENESIS_HASH
        if report.count:
            for _lineno, line in _iter_lines(self.path):
                last_hash = json.loads(line)["hash"]
        return report.count, last_hash

    def verify(self) -> VerifyReport:
        return verify_file(self.path)

    def envelopes(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for _lineno, line in _iter_lines(self.path)]

    def records(self) -> list[dict]:
        """The stored (redacted) evidence records, in append order."""
        return [env["record"] for env in self.envelopes()]

    # -- writing ------------------------------------------------------

    def append(self, record: dict, *, validate: bool = True) -> dict:
        """Redact, validate and append ``record``; return the stored envelope.

        The file is only ever opened in append mode: prior bytes are
        never overwritten or mutated.
        """
        stored = _redact.redact_record(record)
        if validate:
            _validate.validate(stored, "evidence")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        seq, prev_hash = self._tail()
        envelope = {
            "seq": seq,
            "prev_hash": prev_hash,
            "hash": chain_hash(prev_hash, stored),
            "record": stored,
        }
        line = canonical_bytes(envelope).decode("utf-8") + "\n"
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        return envelope
