# AGENTS.md

Guide for AI coding agents working on this codebase.

## Project Overview

**handoff-guard** is a lightweight Python library that validates data at agent/pipeline boundaries using Pydantic schemas. It wraps functions with a `@guard` decorator that validates output, retries with feedback on failure, and raises rich `HandoffViolation` exceptions identifying the exact node, field, and suggested fix.

- **Package name (PyPI):** `handoff-guard`
- **Import name:** `handoff`
- **Python:** >= 3.10
- **Core dependency:** Pydantic >= 2.0

## Repository Structure

```
src/handoff/           # Library source code
  __init__.py          # Public API exports
  core.py              # ViolationContext dataclass, HandoffViolation exception
  guard.py             # @guard decorator, retry loop, validation logic
  retry.py             # RetryState, Diagnostic, AttemptRecord, _RetryProxy (retry singleton)
  utils.py             # parse_json(), ParseError
  testing.py           # mock_retry() context manager for tests
  langgraph.py         # LangGraph adapter: guarded_node, validate_state

tests/
  test_guard.py        # Guard decorator tests (sync, async, on_fail modes)
  test_retry.py        # Retry loop, proxy, history, parse error retry tests
  test_testing.py      # mock_retry tests
  test_utils.py        # parse_json tests

examples/
  llm_demo/            # Multi-agent pipeline (Planner -> Researcher -> Writer)
    __init__.py
    schemas.py         # PlannerOutput, ResearcherOutput, WriterOutput
    agents.py          # Guarded agents with retry, module-level _mock_responses
    run_demo.py        # Entry point: python -m examples.llm_demo.run_demo
    README.md
  rag_demo/            # RAG pipeline (Parser -> Retriever -> Reranker -> Generator)
    __init__.py
    schemas.py         # ParsedQuery, RetrievedDocs, RankedDocs, RAGOutput, etc.
    pipeline.py        # Guarded pipeline stages with retry on generator
    run_demo.py        # Entry point: python -m examples.rag_demo.run_demo
    README.md

.github/workflows/
  ci.yml               # Tests on Python 3.10/3.11/3.12 + ruff lint
  publish.yml          # Auto-publish to PyPI on GitHub release
```

## Key Concepts

### Public API

```python
from handoff import guard, GuardConfig, HandoffViolation, ViolationContext
from handoff import retry, RetryState, Diagnostic, AttemptRecord
from handoff import parse_json, ParseError
from handoff.langgraph import guarded_node, validate_state
```

### `@guard` decorator

```python
@guard(
    input=Schema,              # Pydantic model for input validation
    output=Schema,             # Pydantic model for output validation
    node_name="...",           # Identifies the node in errors (default: function name)
    max_attempts=3,            # Retry up to N times (default: 1, no retry)
    retry_on=("validation", "parse"),  # Error types that trigger retry
    on_fail="raise",           # "raise" | "return_none" | "return_input" | callable
)
```

- Input validation happens once, outside the retry loop
- Output validation happens inside the retry loop
- Parse errors (`ParseError`, `json.JSONDecodeError`, `KeyError`, `TypeError`) are retried when `"parse"` is in `retry_on`
- If the function has a `retry` parameter, `RetryState` is auto-injected

### `retry` proxy

Module-level singleton that reads from a ContextVar, safe to use anywhere:

```python
from handoff import retry

retry.is_retry          # True if attempt > 1
retry.attempt           # Current attempt number (1-based)
retry.max_attempts      # Total allowed attempts
retry.remaining         # Attempts left
retry.is_final_attempt  # True if no more retries
retry.feedback()        # Formatted error string from last attempt, or None
retry.last_error        # Diagnostic object, or None
retry.history           # List of AttemptRecord
```

### `parse_json`

Parses JSON from LLM text output, stripping markdown code fences and BOM. Raises `ParseError` (retryable by `@guard`) on failure.

### `HandoffViolation`

Exception with:
- `.context` — `ViolationContext` (node_name, contract_type, field_path, expected, received, suggestion)
- `.history` — `list[AttemptRecord]` (empty if no retries)
- `.node_name`, `.field_path` — shortcuts
- `.total_attempts` — `len(history)` or 1
- `.to_dict()` — serializable for logging

### on_fail modes

- `"raise"` — Raise HandoffViolation (default)
- `"return_none"` — Return None
- `"return_input"` — Return the original input unchanged
- `callable` — Call with the HandoffViolation, return its result

### Suggestion generation

Auto-generated in `guard.py:_generate_suggestion` based on Pydantic error types: `missing`, `string_type`, `int_type`, `string_too_short`, `string_too_long`, `too_short`, `too_long`, `greater_than_equal`, `less_than_equal`, `string_pattern_mismatch`. Add new error types there.

## Development Commands

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run LLM demo (no API key needed)
python -m examples.llm_demo.run_demo                # retry demo (default)
python -m examples.llm_demo.run_demo --failure-demo  # exhausted retries
python -m examples.llm_demo.run_demo --pipeline      # mock pipeline

# Run RAG demo (no API key needed)
python -m examples.rag_demo.run_demo                 # pipeline + hallucination check

# Run with real LLM calls (needs OPENROUTER_API_KEY)
python -m examples.llm_demo.run_demo --pipeline --api
python -m examples.rag_demo.run_demo --api

# Lint
ruff check src/ tests/ examples/

# Build package
python -m build
```

## Architecture Decisions

- **Pydantic v2 only** — Uses `model_validate`, `model_dump`, not v1 API
- **No runtime deps beyond Pydantic** — LangGraph/httpx are optional
- **Sync and async** — `@guard` detects `async def` and wraps accordingly
- **First violation wins** — Only the first validation error is raised (not all)
- **Dict-oriented** — Agents typically pass dicts; the decorator validates dicts against Pydantic models without requiring the function to use models directly
- **ContextVar for retry state** — The `retry` proxy uses a ContextVar so it's async-safe and doesn't require passing state through function signatures
- **Input validation outside retry loop** — Input doesn't change between retries, so it's validated once upfront
- **Parse errors retryable** — `ParseError`, `json.JSONDecodeError`, `KeyError`, `TypeError` are caught and retried when `max_attempts > 1`

## Adding New Features

When adding a new error type suggestion, edit `_generate_suggestion` in `src/handoff/guard.py`.

When adding a new framework adapter (e.g., CrewAI), create `src/handoff/crewai.py` following the pattern in `langgraph.py` and export from `__init__.py`.

When adding a new demo, create `examples/<name>_demo/` with `__init__.py`, `schemas.py`, `run_demo.py` and a `README.md`. Run it with `python -m examples.<name>_demo.run_demo`.

## Testing

Tests are split across four files:

- `test_guard.py` — Guard decorator: valid passthrough, invalid input/output raises, on_fail modes, custom node_name, input/output-only, async support, violation context and serialization
- `test_retry.py` — Retry loop: succeeds on later attempt, exhausts max_attempts, RetryState injection, proxy behavior, feedback text, violation history, parse error retry, retry_on filtering, on_fail after retry, input validation skips retry, async retry
- `test_testing.py` — `mock_retry()` context manager sets context and proxy works
- `test_utils.py` — `parse_json`: valid JSON, code fence stripping, invalid raises ParseError, non-string raises, BOM stripping

Run with: `pytest tests/ -v`
