"""Schema validation for RAD pipeline records (WP2).

Loads the versioned JSON Schemas in ../schemas and validates records
against them with the ``jsonschema`` package (draft 2020-12). On top of
the schema itself, every property declared ``"format": "date-time"`` is
checked as a real RFC 3339 timestamp, because jsonschema only enforces
``format`` when a format checker is supplied and its date-time checker
depends on optional packages.

Errors are returned (or raised) as specific strings of the form
``<json-path>: <what is wrong>`` -- missing fields, wrong types, unknown
enum values, pattern mismatches, unexpected properties, bad timestamps.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import jsonschema
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

_KIND_TO_FILE = {
    "cycle": "cycle.schema.json",
    "stage": "stage.schema.json",
    "finding": "finding.schema.json",
    "artifact_link": "artifact-link.schema.json",
    "approval": "approval.schema.json",
    "evidence": "evidence.schema.json",
}

KINDS = tuple(_KIND_TO_FILE)


class ValidationError(Exception):
    """Raised when a record fails validation; carries every error found."""

    def __init__(self, kind: str, errors: Iterable[str]):
        self.kind = kind
        self.errors = list(errors)
        super().__init__(
            f"{kind} record failed validation with {len(self.errors)} error(s): "
            + "; ".join(self.errors)
        )


@lru_cache(maxsize=None)
def load_schema(kind: str) -> dict:
    """Load (and meta-validate) the schema for ``kind``."""
    try:
        filename = _KIND_TO_FILE[kind]
    except KeyError:
        raise ValueError(
            f"unknown record kind {kind!r}; expected one of {sorted(_KIND_TO_FILE)}"
        ) from None
    with open(SCHEMA_DIR / filename, encoding="utf-8") as fh:
        schema = json.load(fh)
    Draft202012Validator.check_schema(schema)
    return schema


def _json_path(parts: Iterable[Any]) -> str:
    out = "$"
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}"
    return out


_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _is_rfc3339(value: str) -> bool:
    if not _RFC3339_RE.match(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _datetime_errors(schema: Any, value: Any, path: tuple = ()) -> list[str]:
    """Walk schema+value in parallel; check every format=date-time string."""
    errors: list[str] = []
    if not isinstance(schema, dict):
        return errors
    if schema.get("format") == "date-time" and isinstance(value, str):
        if not _is_rfc3339(value):
            errors.append(
                f"{_json_path(path)}: {value!r} is not a valid RFC 3339 date-time"
            )
        return errors
    if isinstance(value, dict):
        for key, subschema in schema.get("properties", {}).items():
            if key in value:
                errors += _datetime_errors(subschema, value[key], path + (key,))
    elif isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors += _datetime_errors(item_schema, item, path + (index,))
    return errors


def check(record: Any, kind: str) -> list[str]:
    """Return a list of validation errors for ``record`` (empty = valid)."""
    schema = load_schema(kind)
    validator = Draft202012Validator(schema)
    errors = [
        f"{_json_path(err.absolute_path)}: {err.message}"
        for err in sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path))
    ]
    errors += _datetime_errors(schema, record)
    if not errors:
        # Schema-valid but semantically impossible orderings worth a hard error:
        errors += _ordering_errors(record, kind)
    return errors


def _ordering_errors(record: Any, kind: str) -> list[str]:
    errors: list[str] = []
    if isinstance(record, dict) and kind == "stage":
        started, completed = record.get("started_at"), record.get("completed_at")
        if (
            isinstance(started, str)
            and isinstance(completed, str)
            and _is_rfc3339(started)
            and _is_rfc3339(completed)
            and datetime.fromisoformat(completed.replace("Z", "+00:00"))
            < datetime.fromisoformat(started.replace("Z", "+00:00"))
        ):
            errors.append("$.completed_at: completed_at is before started_at")
    return errors


def validate(record: Any, kind: str) -> None:
    """Validate ``record`` as ``kind``; raise ValidationError listing all problems."""
    errors = check(record, kind)
    if errors:
        raise ValidationError(kind, errors)


# Convenience wrappers -------------------------------------------------

def validate_cycle(record: Any) -> None:
    validate(record, "cycle")


def validate_stage(record: Any) -> None:
    validate(record, "stage")


def validate_finding(record: Any) -> None:
    validate(record, "finding")


def validate_artifact_link(record: Any) -> None:
    validate(record, "artifact_link")


def validate_approval(record: Any) -> None:
    validate(record, "approval")


def validate_evidence(record: Any) -> None:
    validate(record, "evidence")
