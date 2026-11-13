"""RAD pipeline core package.

WP2: contracts and evidence store (validate, evidence, redact).
WP3: orchestration core (statemachine, policy, executor, scheduler).
"""

from . import evidence, executor, policy, redact, scheduler, statemachine, validate

__all__ = [
    "evidence",
    "executor",
    "policy",
    "redact",
    "scheduler",
    "statemachine",
    "validate",
]
__version__ = "0.1"
