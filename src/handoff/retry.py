"""Retry-with-feedback data structures and async-safe proxy."""

from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

RetryCause = Literal["validation", "parse"]

_RAW_OUTPUT_MAX = 500
_FEEDBACK_MAX_DEFAULT = 2000


@dataclass
class Diagnostic:
    """Describes why an attempt failed."""

    cause: RetryCause
    message: str
    errors: list[str] = field(default_factory=list)
    raw_output: str | None = None
    field_path: str | None = None
    suggestion: str | None = None

    def __post_init__(self):
        if self.raw_output and len(self.raw_output) > _RAW_OUTPUT_MAX:
            self.raw_output = self.raw_output[:_RAW_OUTPUT_MAX]


@dataclass
class AttemptRecord:
    """Record of a single attempt."""

    attempt: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    diagnostic: Diagnostic | None = None
    duration_ms: float | None = None


@dataclass
class RetryState:
    """Current retry state passed to functions."""

    attempt: int = 1
    max_attempts: int = 1
    last_error: Diagnostic | None = None
    history: list[AttemptRecord] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(0, self.max_attempts - self.attempt)

    @property
    def is_retry(self) -> bool:
        return self.attempt > 1

    @property
    def is_final_attempt(self) -> bool:
        return self.attempt >= self.max_attempts

    def feedback(self, max_chars: int = _FEEDBACK_MAX_DEFAULT) -> str | None:
        if self.last_error is None:
            return None
        text = _format_diagnostic(self.last_error)
        if len(text) > max_chars:
            text = text[:max_chars]
        return text


def _format_diagnostic(diag: Diagnostic) -> str:
    """Render a Diagnostic as LLM-friendly text."""
    lines = [
        f"[Retry] Previous attempt failed ({diag.cause}):",
        f"  Message: {diag.message}",
    ]
    if diag.errors:
        lines.append("  Errors:")
        for err in diag.errors:
            lines.append(f"    - {err}")
    if diag.field_path:
        lines.append(f"  Field: {diag.field_path}")
    if diag.suggestion:
        lines.append(f"  Suggestion: {diag.suggestion}")
    if diag.raw_output:
        lines.append(f"  Raw output: {diag.raw_output}")
    return "\n".join(lines)


_retry_context: ContextVar[RetryState | None] = ContextVar(
    "_retry_context", default=None
)


class _RetryProxy:
    """Reads from _retry_context, exposes RetryState interface with safe defaults."""

    def _get(self) -> RetryState | None:
        return _retry_context.get(None)

    def get(self) -> RetryState | None:
        return self._get()

    @property
    def attempt(self) -> int:
        state = self._get()
        return state.attempt if state else 1

    @property
    def max_attempts(self) -> int:
        state = self._get()
        return state.max_attempts if state else 1

    @property
    def remaining(self) -> int:
        state = self._get()
        return state.remaining if state else 0

    @property
    def is_retry(self) -> bool:
        state = self._get()
        return state.is_retry if state else False

    @property
    def is_final_attempt(self) -> bool:
        state = self._get()
        return state.is_final_attempt if state else True

    @property
    def last_error(self) -> Diagnostic | None:
        state = self._get()
        return state.last_error if state else None

    @property
    def history(self) -> list[AttemptRecord]:
        state = self._get()
        return state.history if state else []

    def feedback(self, max_chars: int = _FEEDBACK_MAX_DEFAULT) -> str | None:
        state = self._get()
        if state is None:
            return None
        return state.feedback(max_chars)


retry = _RetryProxy()
