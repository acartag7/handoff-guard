"""LangGraph-specific utilities for handoff validation."""

from typing import Any, Type, Callable, TypeVar
from pydantic import BaseModel

from handoff.guard import guard
from handoff.core import HandoffViolation


T = TypeVar("T")


def guarded_node(
    input: Type[BaseModel] | None = None,
    output: Type[BaseModel] | None = None,
    *,
    max_attempts: int = 1,
    retry_on: tuple[str, ...] = ("validation", "parse"),
    on_fail: str | Callable[[HandoffViolation], Any] = "raise",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    LangGraph-specific decorator for node validation.

    Wraps @guard with LangGraph-friendly defaults.

    Example:
        from handoff.langgraph import guarded_node

        class AgentInput(BaseModel):
            messages: list
            context: dict

        class AgentOutput(BaseModel):
            messages: list
            next_agent: str

        @guarded_node(input=AgentInput, output=AgentOutput)
        def my_agent(state: dict) -> dict:
            # Your agent logic
            return {"messages": [...], "next_agent": "reviewer"}
    """
    return guard(
        input=input,
        output=output,
        max_attempts=max_attempts,
        retry_on=retry_on,
        on_fail=on_fail,
    )


def validate_state(
    state: dict | BaseModel,
    schema: Type[BaseModel],
    node_name: str = "unknown",
) -> BaseModel:
    """
    Explicitly validate state against a schema.

    Use this for manual validation points, e.g., before checkpointing.

    Raises:
        HandoffViolation: If validation fails

    Example:
        validated = validate_state(state, MyStateSchema, node_name="pre_checkpoint")
    """
    from handoff.guard import _validate_data

    success, validated, violations = _validate_data(
        state, schema, node_name, "state"
    )

    if not success:
        raise HandoffViolation(violations[0])

    return validated
