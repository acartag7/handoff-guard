"""LLM-powered agents with retry-with-feedback."""

import os

from handoff import guard, retry, parse_json
from .schemas import PlannerOutput, ResearcherOutput, WriterOutput


OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"

# Module-level mock responses, keyed by agent name.
# Set before calling an agent to control its output per attempt.
# Example: _mock_responses["writer"] = [attempt1_dict, attempt2_dict, ...]
_mock_responses: dict[str, list[dict]] = {}

# Tracks the last attempt number for display after a successful call.
_current_attempt: int = 1


def call_llm(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
) -> str:
    """Call OpenRouter API."""
    import httpx

    if not OPENROUTER_API_KEY:
        raise ValueError("Set OPENROUTER_API_KEY environment variable")

    response = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _log_attempt():
    """Print retry status. Call at the top of guarded agents to show attempt progress."""
    global _current_attempt
    _current_attempt = retry.attempt
    if retry.is_retry and retry.last_error:
        err = retry.last_error
        detail = err.errors[0] if err.errors else err.message
        print(f"  Attempt {retry.attempt - 1}/{retry.max_attempts}: \u274c {detail}")
        print(f"    \u2192 Retrying with feedback...")


def _get_mock(name: str) -> dict | None:
    """Get mock response for current attempt, or None if no mocks set."""
    responses = _mock_responses.get(name)
    if responses is None:
        return None
    idx = min(retry.attempt - 1, len(responses) - 1)
    return responses[idx]


@guard(output=PlannerOutput, node_name="planner", max_attempts=3)
def planner_agent(state: dict, *, use_llm: bool = False) -> dict:
    """Plan content structure."""
    _log_attempt()
    user_request = state.get("user_request", "Write about AI agents")

    prompt = f"""You are a content planner.
Output ONLY valid JSON with this structure:
{{"topic": "...", "questions": ["...", "..."], "tone": "formal|casual|technical"}}

Plan content for: {user_request}"""

    if retry.is_retry:
        prompt += f"\n\n{retry.feedback()}"

    if use_llm:
        response = call_llm([
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Plan content for: {user_request}"},
        ])
        return parse_json(response)

    mock = _get_mock("planner")
    if mock is not None:
        return mock

    return {
        "topic": user_request,
        "questions": ["What is it?", "Why does it matter?", "What are the challenges?"],
        "tone": "technical",
    }


@guard(output=ResearcherOutput, node_name="researcher", max_attempts=3)
def researcher_agent(state: dict, *, use_llm: bool = False) -> dict:
    """Research a topic."""
    _log_attempt()
    plan = state["plan"]

    prompt = f"""You are a researcher.
Output ONLY valid JSON with this structure:
{{"topic": "...", "facts": ["...", "..."], "sources": ["..."], "questions_answered": N}}

Research this topic: {plan['topic']}
Questions: {plan.get('questions', [])}"""

    if retry.is_retry:
        prompt += f"\n\n{retry.feedback()}"

    if use_llm:
        response = call_llm([
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Research: {plan['topic']}"},
        ])
        return parse_json(response)

    mock = _get_mock("researcher")
    if mock is not None:
        return mock

    return {
        "topic": plan["topic"],
        "facts": [
            "LLM agents can perform complex multi-step tasks autonomously.",
            "Validation at agent boundaries prevents cascading failures.",
            "Retry with feedback allows agents to self-correct output errors.",
        ],
        "sources": ["arxiv.org", "docs.python.org"],
        "questions_answered": 3,
    }


@guard(output=WriterOutput, node_name="writer", max_attempts=3)
def writer_agent(state: dict, *, use_llm: bool = False) -> dict:
    """Write content from research."""
    _log_attempt()
    research = state["research"]
    plan = state["plan"]

    prompt = f"""You are a writer.
Output ONLY valid JSON with this structure:
{{"draft": "...", "word_count": N, "tone": "...", "title": "..."}}

Write about {research['topic']} using these facts: {research['facts']}. Tone: {plan.get('tone', 'technical')}
The draft must be at least 100 characters and the word_count must be at least 50."""

    if retry.is_retry:
        prompt += f"\n\n{retry.feedback()}"

    if use_llm:
        response = call_llm([
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Write about: {research['topic']}"},
        ])
        return parse_json(response)

    mock = _get_mock("writer")
    if mock is not None:
        return mock

    draft = (
        "LLM agents are transforming software development by enabling autonomous multi-step task execution. "
        "Validation at agent boundaries is critical for preventing cascading failures in multi-agent systems. "
        "With retry-with-feedback, agents can self-correct when their output does not meet the required schema, "
        "making pipelines more robust without manual intervention. By combining structured output validation "
        "with automatic retries, developers can build reliable agent workflows that gracefully handle the "
        "inherent unpredictability of large language model outputs."
    )
    return {
        "draft": draft,
        "word_count": len(draft.split()),
        "tone": plan.get("tone", "technical"),
        "title": f"Understanding {research['topic']}",
    }
