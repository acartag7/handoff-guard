"""The @guard decorator for validating agent boundaries."""

import json
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, TypeVar, Type, Literal
import inspect

from pydantic import BaseModel, ValidationError

from handoff.core import HandoffViolation, ViolationContext
from handoff.retry import (
    _retry_context,
    RetryState,
    Diagnostic,
    AttemptRecord,
)
from handoff.utils import ParseError


T = TypeVar("T")
OnFailAction = Literal["raise", "return_none", "return_input"]


@dataclass
class GuardConfig:
    """Configuration for guard behavior."""

    input_schema: Type[BaseModel] | None = None
    output_schema: Type[BaseModel] | None = None
    node_name: str | None = None  # Auto-detected from function name if not provided
    on_fail: OnFailAction | Callable[[HandoffViolation], Any] = "raise"
    validate_input: bool = True
    validate_output: bool = True


def _generate_suggestion(
    err_type: str, field_path: str, contract_type: str
) -> str | None:
    """Generate a helpful suggestion based on Pydantic error type."""
    if err_type == "missing":
        return f"Add '{field_path}' to the {contract_type} data"
    elif err_type == "string_type":
        return f"Convert '{field_path}' to string"
    elif err_type == "int_type":
        return f"Convert '{field_path}' to integer"
    elif err_type == "string_too_short":
        return f"Increase the length of '{field_path}'"
    elif err_type == "string_too_long":
        return f"Reduce the length of '{field_path}'"
    elif err_type == "too_short":
        return f"Add more items to '{field_path}'"
    elif err_type == "too_long":
        return f"Reduce the number of items in '{field_path}'"
    elif err_type == "greater_than_equal":
        return f"Increase the value of '{field_path}'"
    elif err_type == "less_than_equal":
        return f"Decrease the value of '{field_path}'"
    elif err_type == "string_pattern_mismatch":
        return f"'{field_path}' does not match the required pattern"
    return None


def _extract_violations(
    error: ValidationError,
    node_name: str,
    contract_type: str,
    raw_data: Any,
) -> list[ViolationContext]:
    """Convert Pydantic ValidationError to rich ViolationContext objects."""

    violations = []
    for err in error.errors():
        field_path = ".".join(str(loc) for loc in err["loc"])

        # Try to get the actual value at the path
        received = raw_data
        for loc in err["loc"]:
            if isinstance(received, dict):
                received = received.get(loc, "<missing>")
            elif hasattr(received, str(loc)):
                received = getattr(received, str(loc), "<missing>")
            else:
                received = "<missing>"
                break

        suggestion = _generate_suggestion(err["type"], field_path, contract_type)

        violations.append(
            ViolationContext(
                node_name=node_name,
                contract_type=contract_type,
                field_path=field_path or "<root>",
                expected=err["msg"],
                received=received,
                received_type=type(received).__name__,
                suggestion=suggestion,
            )
        )

    return violations


def _validate_data(
    data: Any,
    schema: Type[BaseModel],
    node_name: str,
    contract_type: str,
) -> tuple[bool, BaseModel | None, list[ViolationContext]]:
    """Validate data against schema, return (success, validated_model, violations)."""

    try:
        # Handle both dict and BaseModel inputs
        if isinstance(data, BaseModel):
            validated = schema.model_validate(data.model_dump())
        elif isinstance(data, dict):
            validated = schema.model_validate(data)
        else:
            # Try to convert to dict
            validated = schema.model_validate(
                data.__dict__ if hasattr(data, "__dict__") else {"value": data}
            )
        return True, validated, []

    except ValidationError as e:
        violations = _extract_violations(e, node_name, contract_type, data)
        return False, None, violations


def _build_validation_diagnostic(
    violations: list[ViolationContext],
    result: Any,
) -> Diagnostic:
    """Build a Diagnostic from output validation violations."""
    errors = [
        f"{v.field_path}: expected {v.expected}, got {repr(v.received)[:100]}"
        for v in violations
    ]
    return Diagnostic(
        cause="validation",
        message="Output validation failed",
        errors=errors,
        raw_output=repr(result)[:500] if result is not None else None,
        field_path=violations[0].field_path if violations else None,
        suggestion=violations[0].suggestion if violations else None,
    )


def _build_parse_diagnostic(exc: Exception, raw: Any = None) -> Diagnostic:
    """Build a Diagnostic from a parse error."""
    raw_output = None
    if isinstance(exc, ParseError):
        raw_output = exc.raw_output
    elif raw is not None:
        raw_output = repr(raw)[:500]
    return Diagnostic(
        cause="parse",
        message=str(exc),
        raw_output=raw_output,
    )


def guard(
    input: Type[BaseModel] | None = None,
    output: Type[BaseModel] | None = None,
    *,
    node_name: str | None = None,
    max_attempts: int = 1,
    retry_on: tuple[str, ...] = ("validation", "parse"),
    on_fail: OnFailAction | Callable[[HandoffViolation], Any] = "raise",
    input_param: str | None = "state",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to validate input/output at agent boundaries.

    Args:
        input: Pydantic model to validate input against
        output: Pydantic model to validate output against
        node_name: Override the node name (defaults to function name)
        max_attempts: Maximum number of attempts (1 = no retry, default)
        retry_on: Tuple of error types to retry on ("validation", "parse")
        on_fail: What to do on validation failure:
            - "raise": Raise HandoffViolation (default)
            - "return_none": Return None
            - "return_input": Return input unchanged
            - callable: Call with HandoffViolation, return its result
        input_param: Name of the input argument to validate (default: "state")

    Example:
        @guard(input=RequestSchema, output=ResponseSchema)
        def my_agent_node(state: dict) -> dict:
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        _node_name = node_name or func.__name__
        is_async = inspect.iscoroutinefunction(func)

        # Check if function accepts a 'retry' parameter
        sig = inspect.signature(func)
        _accepts_retry = "retry" in sig.parameters

        def _bind_input(args: tuple, kwargs: dict) -> Any:
            """Extract the input argument using signature binding."""
            if input_param is None:
                if args:
                    return args[0]
                return kwargs.get("state")
            try:
                bound = sig.bind_partial(*args, **kwargs)
            except TypeError:
                return kwargs.get(input_param)
            if input_param in bound.arguments:
                return bound.arguments[input_param]
            return kwargs.get(input_param)

        def _handle_violation(violation: HandoffViolation, input_data: Any) -> Any:
            if on_fail == "raise":
                raise violation
            elif on_fail == "return_none":
                return None
            elif on_fail == "return_input":
                return input_data
            elif callable(on_fail):
                return on_fail(violation)
            else:
                raise violation

        def _validate_input(
            args: tuple, kwargs: dict
        ) -> tuple[Any, list[ViolationContext]]:
            if not input:
                return _bind_input(args, kwargs), []

            input_data = _bind_input(args, kwargs)

            success, validated, violations = _validate_data(
                input_data, input, _node_name, "input"
            )

            if not success:
                return input_data, violations

            return input_data, []

        def _validate_output_data(result: Any) -> list[ViolationContext]:
            if not output:
                return []

            success, validated, violations = _validate_data(
                result, output, _node_name, "output"
            )

            return violations

        def _is_retryable_parse_error(exc: Exception) -> bool:
            """Check if exception is a parse-related error eligible for retry."""
            return isinstance(exc, (ParseError, json.JSONDecodeError))

        if is_async:

            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                # Validate input (outside retry loop — input doesn't change)
                input_data, input_violations = _validate_input(args, kwargs)
                if input_violations:
                    violation = HandoffViolation(input_violations[0])
                    return _handle_violation(violation, input_data)

                history: list[AttemptRecord] = []
                last_diagnostic: Diagnostic | None = None

                for attempt_num in range(1, max_attempts + 1):
                    state = RetryState(
                        attempt=attempt_num,
                        max_attempts=max_attempts,
                        last_error=last_diagnostic,
                        history=list(history),
                    )
                    token = _retry_context.set(state)
                    start_time = time.monotonic()
                    try:
                        # Inject retry kwarg if function accepts it
                        call_kwargs = dict(kwargs)
                        if _accepts_retry and "retry" not in call_kwargs:
                            call_kwargs["retry"] = state

                        try:
                            result = await func(*args, **call_kwargs)
                        except Exception as exc:
                            if _is_retryable_parse_error(exc) and "parse" in retry_on:
                                elapsed = (time.monotonic() - start_time) * 1000
                                diag = _build_parse_diagnostic(
                                    exc, getattr(exc, "raw_output", None)
                                )
                                last_diagnostic = diag
                                history.append(
                                    AttemptRecord(
                                        attempt=attempt_num,
                                        diagnostic=diag,
                                        duration_ms=elapsed,
                                    )
                                )
                                if attempt_num < max_attempts:
                                    continue
                                # Final attempt — build violation
                                violation_ctx = ViolationContext(
                                    node_name=_node_name,
                                    contract_type="output",
                                    field_path="<parse>",
                                    expected="Valid parseable output",
                                    received=str(exc),
                                    received_type=type(exc).__name__,
                                    suggestion="Return valid JSON or structured data",
                                )
                                violation = HandoffViolation(
                                    violation_ctx, history=history
                                )
                                return _handle_violation(violation, input_data)
                            else:
                                raise

                        # Validate output
                        output_violations = _validate_output_data(result)
                        elapsed = (time.monotonic() - start_time) * 1000
                        if output_violations:
                            diag = _build_validation_diagnostic(
                                output_violations, result
                            )
                            last_diagnostic = diag
                            history.append(
                                AttemptRecord(
                                    attempt=attempt_num,
                                    diagnostic=diag,
                                    duration_ms=elapsed,
                                )
                            )
                            if "validation" in retry_on and attempt_num < max_attempts:
                                continue
                            # Final attempt or validation not retried
                            violation = HandoffViolation(
                                output_violations[0], history=history
                            )
                            return _handle_violation(violation, input_data)

                        # Success
                        history.append(
                            AttemptRecord(
                                attempt=attempt_num,
                                duration_ms=elapsed,
                            )
                        )
                        return result

                    finally:
                        _retry_context.reset(token)

            return async_wrapper

        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                # Validate input (outside retry loop — input doesn't change)
                input_data, input_violations = _validate_input(args, kwargs)
                if input_violations:
                    violation = HandoffViolation(input_violations[0])
                    return _handle_violation(violation, input_data)

                history: list[AttemptRecord] = []
                last_diagnostic: Diagnostic | None = None

                for attempt_num in range(1, max_attempts + 1):
                    state = RetryState(
                        attempt=attempt_num,
                        max_attempts=max_attempts,
                        last_error=last_diagnostic,
                        history=list(history),
                    )
                    token = _retry_context.set(state)
                    start_time = time.monotonic()
                    try:
                        # Inject retry kwarg if function accepts it
                        call_kwargs = dict(kwargs)
                        if _accepts_retry and "retry" not in call_kwargs:
                            call_kwargs["retry"] = state

                        try:
                            result = func(*args, **call_kwargs)
                        except Exception as exc:
                            if (
                                _is_retryable_parse_error(exc)
                                and "parse" in retry_on
                                and max_attempts > 1
                            ):
                                elapsed = (time.monotonic() - start_time) * 1000
                                diag = _build_parse_diagnostic(
                                    exc, getattr(exc, "raw_output", None)
                                )
                                last_diagnostic = diag
                                history.append(
                                    AttemptRecord(
                                        attempt=attempt_num,
                                        diagnostic=diag,
                                        duration_ms=elapsed,
                                    )
                                )
                                if attempt_num < max_attempts:
                                    continue
                                # Final attempt — build violation
                                violation_ctx = ViolationContext(
                                    node_name=_node_name,
                                    contract_type="output",
                                    field_path="<parse>",
                                    expected="Valid parseable output",
                                    received=str(exc),
                                    received_type=type(exc).__name__,
                                    suggestion="Return valid JSON or structured data",
                                )
                                violation = HandoffViolation(
                                    violation_ctx, history=history
                                )
                                return _handle_violation(violation, input_data)
                            else:
                                raise

                        # Validate output
                        output_violations = _validate_output_data(result)
                        elapsed = (time.monotonic() - start_time) * 1000
                        if output_violations:
                            diag = _build_validation_diagnostic(
                                output_violations, result
                            )
                            last_diagnostic = diag
                            history.append(
                                AttemptRecord(
                                    attempt=attempt_num,
                                    diagnostic=diag,
                                    duration_ms=elapsed,
                                )
                            )
                            if "validation" in retry_on and attempt_num < max_attempts:
                                continue
                            # Final attempt or validation not retried
                            violation = HandoffViolation(
                                output_violations[0], history=history
                            )
                            return _handle_violation(violation, input_data)

                        # Success
                        history.append(
                            AttemptRecord(
                                attempt=attempt_num,
                                duration_ms=elapsed,
                            )
                        )
                        return result

                    finally:
                        _retry_context.reset(token)

            return sync_wrapper

    return decorator
