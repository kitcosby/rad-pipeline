"""Redaction of secrets before persistence (WP2).

Two rules, applied recursively to any JSON-shaped value:

1. Key rule -- in a mapping, if the key contains any of the substrings
   KEY, TOKEN, SECRET, PASSWORD or AUTH (case-insensitive, per the WP2
   work-package text: keys matching *KEY*, *TOKEN*, *SECRET*, *PASSWORD*,
   *AUTH*), the whole value is replaced with REDACTED.
   Implemented literally as a substring match; note this also catches
   innocuous keys such as "author" (*AUTH*) or "monkey" (*KEY*).
   Flagged as an open question in README-WP2.md.

2. Value rule -- string values are scanned for credential-shaped
   substrings regardless of the key they sit under:
   PEM private-key blocks, AWS access key ids (AKIA...), GitHub token
   prefixes (ghp_/gho_/ghu_/ghs_/ghr_/github_pat_), HTTP Bearer tokens,
   passwords embedded in URLs (scheme://user:password@host), and JWTs.
   A matched substring is replaced with REDACTED.

The input is never mutated; a redacted deep copy is returned.
"""

from __future__ import annotations

import copy
import re
from typing import Any

REDACTED = "***REDACTED***"

_SECRET_KEY_SUBSTRINGS = ("key", "token", "secret", "password", "auth")

_VALUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private-key block",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "github token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-+/=]+", re.IGNORECASE)),
    (
        "url password",
        re.compile(r"(://[^/\s:@]+:)([^@/\s]+)(@)"),
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    ),
]


def _key_is_secret(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(sub in lowered for sub in _SECRET_KEY_SUBSTRINGS)


def _redact_string(value: str) -> str:
    out = value
    for _name, pattern in _VALUE_PATTERNS:
        if pattern.pattern.startswith("(://"):
            out = pattern.sub(lambda m: m.group(1) + REDACTED + m.group(3), out)
        else:
            out = pattern.sub(REDACTED, out)
    return out


def redact(value: Any) -> Any:
    """Return a redacted deep copy of ``value``; the input is not mutated."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if _key_is_secret(key) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        items = [redact(item) for item in value]
        return type(value)(items) if isinstance(value, tuple) else items
    if isinstance(value, str):
        return _redact_string(value)
    return copy.deepcopy(value)


# Backwards-friendly alias: the evidence writer talks about "records".
redact_record = redact
