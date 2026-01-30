"""Tests for handoff validation."""

import pytest
from pydantic import BaseModel, Field
from handoff import guard, HandoffViolation


class SimpleInput(BaseModel):
    name: str
    value: int


class SimpleOutput(BaseModel):
    result: str
    processed: bool


class TestGuardDecorator:
    """Test the @guard decorator."""

    def test_valid_input_and_output(self):
        """Should pass with valid data."""
        @guard(input=SimpleInput, output=SimpleOutput)
        def my_func(state: dict) -> dict:
            return {"result": f"Hello {state['name']}", "processed": True}

        result = my_func({"name": "World", "value": 42})
        assert result["result"] == "Hello World"
        assert result["processed"] is True

    def test_invalid_input_raises(self):
        """Should raise HandoffViolation on invalid input."""
        @guard(input=SimpleInput, output=SimpleOutput)
        def my_func(state: dict) -> dict:
            return {"result": "ok", "processed": True}

        with pytest.raises(HandoffViolation) as exc_info:
            my_func({"name": "Test"})  # Missing 'value'

        assert exc_info.value.node_name == "my_func"
        assert "value" in exc_info.value.field_path

    def test_invalid_output_raises(self):
        """Should raise HandoffViolation on invalid output."""
        @guard(input=SimpleInput, output=SimpleOutput)
        def my_func(state: dict) -> dict:
            return {"result": "ok"}  # Missing 'processed'

        with pytest.raises(HandoffViolation) as exc_info:
            my_func({"name": "Test", "value": 1})

        assert exc_info.value.node_name == "my_func"
        assert "processed" in exc_info.value.field_path

    def test_on_fail_return_none(self):
        """Should return None on failure when configured."""
        @guard(input=SimpleInput, output=SimpleOutput, on_fail="return_none")
        def my_func(state: dict) -> dict:
            return {"result": "ok"}  # Invalid output

        result = my_func({"name": "Test", "value": 1})
        assert result is None

    def test_on_fail_return_input(self):
        """Should return input on failure when configured."""
        @guard(input=SimpleInput, output=SimpleOutput, on_fail="return_input")
        def my_func(state: dict) -> dict:
            return {"result": "ok"}  # Invalid output

        input_data = {"name": "Test", "value": 1}
        result = my_func(input_data)
        assert result == input_data

    def test_on_fail_custom_handler(self):
        """Should call custom handler on failure."""
        fallback = {"result": "fallback", "processed": False}

        @guard(input=SimpleInput, output=SimpleOutput, on_fail=lambda e: fallback)
        def my_func(state: dict) -> dict:
            return {"result": "ok"}  # Invalid output

        result = my_func({"name": "Test", "value": 1})
        assert result == fallback

    def test_custom_node_name(self):
        """Should use custom node name in violations."""
        @guard(input=SimpleInput, node_name="custom_name")
        def my_func(state: dict) -> dict:
            return state

        with pytest.raises(HandoffViolation) as exc_info:
            my_func({"name": "Test"})  # Missing 'value'

        assert exc_info.value.node_name == "custom_name"

    def test_output_only_validation(self):
        """Should work with output validation only."""
        @guard(output=SimpleOutput)
        def my_func(state: dict) -> dict:
            return {"result": "ok"}  # Missing 'processed'

        with pytest.raises(HandoffViolation):
            my_func({"anything": "goes"})

    def test_input_only_validation(self):
        """Should work with input validation only."""
        @guard(input=SimpleInput)
        def my_func(state: dict) -> dict:
            return {"anything": "goes"}  # No output validation

        # Valid input should pass
        result = my_func({"name": "Test", "value": 1})
        assert result == {"anything": "goes"}

        # Invalid input should fail
        with pytest.raises(HandoffViolation):
            my_func({"name": "Test"})  # Missing 'value'


class TestAsyncGuard:
    """Test async function support."""

    @pytest.mark.asyncio
    async def test_async_valid(self):
        """Should work with async functions."""
        @guard(input=SimpleInput, output=SimpleOutput)
        async def my_async_func(state: dict) -> dict:
            return {"result": "async ok", "processed": True}

        result = await my_async_func({"name": "Async", "value": 99})
        assert result["result"] == "async ok"

    @pytest.mark.asyncio
    async def test_async_invalid_raises(self):
        """Should raise on invalid async output."""
        @guard(input=SimpleInput, output=SimpleOutput)
        async def my_async_func(state: dict) -> dict:
            return {"result": "ok"}  # Missing 'processed'

        with pytest.raises(HandoffViolation):
            await my_async_func({"name": "Test", "value": 1})


class TestViolationContext:
    """Test violation context quality."""

    def test_violation_has_suggestion(self):
        """Violations should include helpful suggestions."""
        @guard(input=SimpleInput)
        def my_func(state: dict) -> dict:
            return state

        with pytest.raises(HandoffViolation) as exc_info:
            my_func({"name": "Test"})  # Missing 'value'

        assert exc_info.value.context.suggestion is not None

    def test_violation_to_dict(self):
        """Violations should serialize to dict."""
        @guard(input=SimpleInput)
        def my_func(state: dict) -> dict:
            return state

        with pytest.raises(HandoffViolation) as exc_info:
            my_func({"name": "Test"})

        d = exc_info.value.to_dict()
        assert "node_name" in d
        assert "field_path" in d
        assert "timestamp" in d
