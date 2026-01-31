"""Tests for retry-with-feedback functionality."""

import pytest
from pydantic import BaseModel

from handoff import guard, HandoffViolation
from handoff.retry import retry, RetryState
from handoff.utils import ParseError


class SimpleOutput(BaseModel):
    result: str
    score: int


class TestNoRetryDefault:
    """Backward compatibility: max_attempts=1 behaves like v0.1."""

    def test_no_retry_default(self):
        @guard(output=SimpleOutput)
        def my_func(state: dict) -> dict:
            return {"result": "ok"}  # Missing 'score'

        with pytest.raises(HandoffViolation):
            my_func({"x": 1})

    def test_json_decode_passthrough_single_attempt(self):
        """max_attempts=1: JSONDecodeError propagates as-is."""
        import json

        @guard(output=SimpleOutput)
        def my_func(state: dict) -> dict:
            raise json.JSONDecodeError("bad", "", 0)

        with pytest.raises(json.JSONDecodeError):
            my_func({"x": 1})


class TestRetryLoop:
    """Tests for the retry loop mechanics."""

    def test_retry_succeeds_second_attempt(self):
        call_count = 0

        @guard(output=SimpleOutput, max_attempts=3)
        def my_func(state: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"result": "ok"}  # Missing 'score'
            return {"result": "ok", "score": 42}

        result = my_func({"x": 1})
        assert result["score"] == 42
        assert call_count == 2

    def test_retry_exhausts_max_attempts(self):
        call_count = 0

        @guard(output=SimpleOutput, max_attempts=3)
        def my_func(state: dict) -> dict:
            nonlocal call_count
            call_count += 1
            return {"result": "ok"}  # Always invalid

        with pytest.raises(HandoffViolation):
            my_func({"x": 1})
        assert call_count == 3

    def test_retry_state_injected_to_function(self):
        states_seen = []

        @guard(output=SimpleOutput, max_attempts=3)
        def my_func(state: dict, retry: RetryState = None) -> dict:
            states_seen.append(retry)
            if retry and retry.is_retry:
                return {"result": "fixed", "score": 10}
            return {"result": "bad"}  # Invalid

        result = my_func({"x": 1})
        assert result["score"] == 10
        assert len(states_seen) == 2
        assert states_seen[0].attempt == 1
        assert states_seen[0].is_retry is False
        assert states_seen[1].attempt == 2
        assert states_seen[1].is_retry is True

    def test_user_provided_retry_not_overwritten(self):
        custom = RetryState(attempt=99, max_attempts=99)

        @guard(output=SimpleOutput, max_attempts=2)
        def my_func(state: dict, retry: RetryState = None) -> dict:
            assert retry is custom
            return {"result": "ok", "score": 1}

        my_func({"x": 1}, retry=custom)


class TestRetryProxy:
    """Tests for the module-level retry proxy."""

    def test_retry_proxy_falsy_first_attempt(self):
        seen_is_retry = None

        @guard(output=SimpleOutput, max_attempts=2)
        def my_func(state: dict) -> dict:
            nonlocal seen_is_retry
            if seen_is_retry is None:
                seen_is_retry = retry.is_retry
            return {"result": "ok", "score": 1}

        my_func({"x": 1})
        assert seen_is_retry is False

    def test_retry_proxy_truthy_on_retry(self):
        proxy_values = []

        @guard(output=SimpleOutput, max_attempts=3)
        def my_func(state: dict) -> dict:
            proxy_values.append(retry.is_retry)
            if retry.is_retry:
                return {"result": "ok", "score": 1}
            return {"result": "bad"}

        my_func({"x": 1})
        assert proxy_values[0] is False
        assert proxy_values[1] is True

    def test_retry_feedback_returns_text(self):
        feedback_text = None

        @guard(output=SimpleOutput, max_attempts=3)
        def my_func(state: dict) -> dict:
            nonlocal feedback_text
            if retry.is_retry:
                feedback_text = retry.feedback()
                return {"result": "ok", "score": 1}
            return {"result": "bad"}

        my_func({"x": 1})
        assert feedback_text is not None
        assert (
            "validation" in feedback_text.lower() or "failed" in feedback_text.lower()
        )

    def test_retry_feedback_none_first_attempt(self):
        feedback_text = "sentinel"

        @guard(output=SimpleOutput, max_attempts=2)
        def my_func(state: dict) -> dict:
            nonlocal feedback_text
            if not retry.is_retry:
                feedback_text = retry.feedback()
            return {"result": "ok", "score": 1}

        my_func({"x": 1})
        assert feedback_text is None


class TestViolationHistory:
    """Tests for history tracking in HandoffViolation."""

    def test_retry_history_in_violation(self):
        @guard(output=SimpleOutput, max_attempts=3)
        def my_func(state: dict) -> dict:
            return {"result": "bad"}

        with pytest.raises(HandoffViolation) as exc_info:
            my_func({"x": 1})

        exc = exc_info.value
        assert len(exc.history) == 3
        for i, rec in enumerate(exc.history):
            assert rec.attempt == i + 1
            assert rec.duration_ms is not None

    def test_retry_total_attempts_property(self):
        @guard(output=SimpleOutput, max_attempts=2)
        def my_func(state: dict) -> dict:
            return {"result": "bad"}

        with pytest.raises(HandoffViolation) as exc_info:
            my_func({"x": 1})

        assert exc_info.value.total_attempts == 2

    def test_retry_to_dict_includes_history(self):
        @guard(output=SimpleOutput, max_attempts=2)
        def my_func(state: dict) -> dict:
            return {"result": "bad"}

        with pytest.raises(HandoffViolation) as exc_info:
            my_func({"x": 1})

        d = exc_info.value.to_dict()
        assert "total_attempts" in d
        assert d["total_attempts"] == 2
        assert "history" in d
        assert len(d["history"]) == 2


class TestParseRetry:
    """Tests for parse error retry behavior."""

    def test_parse_error_triggers_retry(self):
        call_count = 0

        @guard(output=SimpleOutput, max_attempts=3)
        def my_func(state: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ParseError("bad json", raw_output="not json")
            return {"result": "ok", "score": 1}

        result = my_func({"x": 1})
        assert result["score"] == 1
        assert call_count == 2

    def test_parse_error_no_retry_when_excluded(self):
        @guard(output=SimpleOutput, max_attempts=3, retry_on=("validation",))
        def my_func(state: dict) -> dict:
            raise ParseError("bad json")

        with pytest.raises(ParseError):
            my_func({"x": 1})


class TestParseRetryEdgeCases:
    """Tests for parse retry edge cases."""

    def test_parse_error_raw_output_truncated_in_diagnostic(self):
        """Diagnostic raw_output should be truncated to 500 chars."""

        @guard(output=SimpleOutput, max_attempts=2)
        def my_func(state: dict) -> dict:
            raise ParseError("bad json", raw_output="x" * 2000)

        with pytest.raises(HandoffViolation) as exc_info:
            my_func({"x": 1})

        last_diag = exc_info.value.history[-1].diagnostic
        assert last_diag is not None
        assert last_diag.raw_output is not None
        assert len(last_diag.raw_output) <= 500

    def test_key_error_not_retried_by_default(self):
        """KeyError should not be treated as a retryable parse error."""
        call_count = 0

        @guard(output=SimpleOutput, max_attempts=3)
        def my_func(state: dict) -> dict:
            nonlocal call_count
            call_count += 1
            raise KeyError("missing")

        with pytest.raises(KeyError):
            my_func({"x": 1})
        assert call_count == 1


class TestOnFailAfterRetry:
    """Tests for on_fail modes after retry exhaustion."""

    def test_on_fail_after_retry_exhausted(self):
        @guard(output=SimpleOutput, max_attempts=2, on_fail="return_none")
        def my_func(state: dict) -> dict:
            return {"result": "bad"}

        result = my_func({"x": 1})
        assert result is None


class TestInputValidationNoRetry:
    """Input validation should not trigger retry."""

    def test_input_validation_no_retry(self):
        from pydantic import BaseModel

        class StrictInput(BaseModel):
            name: str
            value: int

        call_count = 0

        @guard(input=StrictInput, output=SimpleOutput, max_attempts=3)
        def my_func(state: dict) -> dict:
            nonlocal call_count
            call_count += 1
            return {"result": "ok", "score": 1}

        with pytest.raises(HandoffViolation):
            my_func({"name": "test"})  # Missing 'value'

        assert call_count == 0  # Function never called


class TestRetryOnValidationOnly:
    """Test retry_on=("validation",) works correctly."""

    def test_retry_on_validation_only(self):
        call_count = 0

        @guard(output=SimpleOutput, max_attempts=3, retry_on=("validation",))
        def my_func(state: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"result": "bad"}
            return {"result": "ok", "score": 1}

        result = my_func({"x": 1})
        assert result["score"] == 1
        assert call_count == 3


class TestAsyncRetry:
    """Test async function retry."""

    @pytest.mark.asyncio
    async def test_async_retry(self):
        call_count = 0

        @guard(output=SimpleOutput, max_attempts=3)
        async def my_func(state: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"result": "bad"}
            return {"result": "ok", "score": 5}

        result = await my_func({"x": 1})
        assert result["score"] == 5
        assert call_count == 2
