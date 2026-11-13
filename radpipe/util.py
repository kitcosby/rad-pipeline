"""Small shared helpers for the WP3 orchestration core."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def now_rfc3339() -> str:
    """Current UTC time as an RFC 3339 timestamp (seconds precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_evidence_id(prefix: str) -> str:
    """A unique evidence_id with a component-identifying prefix."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
