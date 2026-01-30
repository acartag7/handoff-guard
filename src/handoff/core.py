"""Core types for handoff validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from datetime import datetime, timezone

if TYPE_CHECKING:
    from handoff.retry import AttemptRecord


@dataclass
class ViolationContext:
    """Rich context about where and why validation failed."""

    node_name: str
    contract_type: str  # "input" | "output" | "invariant"
    field_path: str     # e.g., "response.refund_id"
    expected: str       # Human-readable expectation
    received: Any       # What we actually got
    received_type: str  # Type of what we got
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    upstream_node: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        lines = [
            f"HandoffViolation in '{self.node_name}':",
            f"  Contract: {self.contract_type}",
            f"  Field: {self.field_path}",
            f"  Expected: {self.expected}",
            f"  Received: {repr(self.received)[:100]} ({self.received_type})",
        ]
        if self.upstream_node:
            lines.append(f"  Upstream: {self.upstream_node}")
        if self.suggestion:
            lines.append(f"  Suggestion: {self.suggestion}")
        return "\n".join(lines)


class HandoffViolation(Exception):
    """Raised when validation fails at an agent boundary."""

    def __init__(
        self,
        context: ViolationContext,
        history: list[AttemptRecord] | None = None,
    ):
        self.context = context
        self.history: list[AttemptRecord] = history or []
        super().__init__(str(context))

    @property
    def node_name(self) -> str:
        return self.context.node_name

    @property
    def field_path(self) -> str:
        return self.context.field_path

    @property
    def total_attempts(self) -> int:
        return len(self.history) if self.history else 1

    def to_dict(self) -> dict:
        """Serialize for logging/telemetry."""
        d = {
            "node_name": self.context.node_name,
            "contract_type": self.context.contract_type,
            "field_path": self.context.field_path,
            "expected": self.context.expected,
            "received": repr(self.context.received)[:200],
            "received_type": self.context.received_type,
            "timestamp": self.context.timestamp.isoformat(),
            "upstream_node": self.context.upstream_node,
            "suggestion": self.context.suggestion,
        }
        if self.history:
            d["total_attempts"] = self.total_attempts
            d["history"] = [
                {
                    "attempt": rec.attempt,
                    "timestamp": rec.timestamp.isoformat(),
                    "duration_ms": rec.duration_ms,
                    "diagnostic": {
                        "cause": rec.diagnostic.cause,
                        "message": rec.diagnostic.message,
                    }
                    if rec.diagnostic
                    else None,
                }
                for rec in self.history
            ]
        return d
