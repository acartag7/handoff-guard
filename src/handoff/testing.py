"""Test utilities for handoff retry."""

from contextlib import contextmanager

from handoff.retry import (
    _retry_context,
    RetryState,
    Diagnostic,
)


@contextmanager
def mock_retry(
    attempt: int = 2,
    max_attempts: int = 3,
    last_error: Diagnostic | None = None,
    feedback_text: str | None = None,
):
    """Context manager that sets retry state for testing.

    If feedback_text is provided without last_error, creates a simple
    validation Diagnostic with that text as the message.
    """
    if feedback_text and last_error is None:
        last_error = Diagnostic(
            cause="validation",
            message=feedback_text,
        )

    state = RetryState(
        attempt=attempt,
        max_attempts=max_attempts,
        last_error=last_error,
    )
    token = _retry_context.set(state)
    try:
        yield state
    finally:
        _retry_context.reset(token)
