# handoff-guard

> Validation for LLM agents that retries with feedback.

[![PyPI version](https://img.shields.io/pypi/v/handoff-guard)](https://pypi.org/project/handoff-guard/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## The Problem

When an LLM agent returns bad output, you get a generic error and no recovery path:

```
ValidationError: 1 validation error for State
   field required (type=value_error.missing)
```

Which node? Which field? What was passed? Can the agent fix it?

## The Solution

```python
from handoff import guard, retry, parse_json
from pydantic import BaseModel, Field

class WriterOutput(BaseModel):
    draft: str = Field(min_length=100)
    word_count: int = Field(ge=50)
    tone: str
    title: str

@guard(output=WriterOutput, node_name="writer", max_attempts=3)
def writer_agent(state: dict) -> dict:
    prompt = "Write a JSON response with: draft, word_count, tone, title."

    if retry.is_retry:
        prompt += f"\n\nYour previous attempt failed:\n{retry.feedback()}"

    response = call_llm(prompt)
    return parse_json(response)
```

When validation fails, the agent retries with feedback about what went wrong. After all attempts are exhausted:

```
HandoffViolation in 'writer' (attempt 3/3):
  Contract: output
  Field: draft
  Expected: String should have at least 100 characters
  Suggestion: Increase the length of 'draft'
  History: 3 failed attempts
```

## Quick Start

```bash
pip install handoff-guard
```

```bash
# See retry-with-feedback in action (no API key needed)
python -m examples.llm_demo.run_demo

# Run with real LLM calls
export OPENROUTER_API_KEY=your_key
python -m examples.llm_demo.run_demo --pipeline --api
```

## Features

- **Retry with feedback** — Failed outputs are fed back to the agent as context
- **Know which node failed** — No more guessing from stack traces
- **Know which field failed** — Exact path to the problem
- **Get fix suggestions** — Actionable error messages
- **`parse_json`** — Strips code fences, conversational wrappers, handles BOM, repairs malformed JSON (trailing commas, single quotes, unquoted keys, missing braces, comments), raises `ParseError` with actionable line/column info
- **Framework agnostic** — Works with LangGraph, CrewAI, or plain Python
- **Lightweight** — Just Pydantic, no Docker, no telemetry servers

## API

### `@guard` decorator

```python
@guard(
    input=InputSchema,          # Pydantic model for input validation
    output=OutputSchema,        # Pydantic model for output validation
    node_name="my_node",        # Identifies the node in errors (default: function name)
    max_attempts=3,             # Retry up to 3 times (default: 1, no retry)
    retry_on=("validation", "parse"),  # What errors trigger retry (default)
    on_fail="raise",            # "raise" | "return_none" | "return_input" | callable
    input_param="state",        # Name of the input arg to validate (default: "state")
)
```

### `retry` proxy

Access retry state inside any guarded function:

```python
from handoff import retry

retry.is_retry        # True if attempt > 1
retry.attempt         # Current attempt number
retry.max_attempts    # Total allowed attempts
retry.remaining       # Attempts left
retry.is_final_attempt
retry.feedback()      # Formatted string describing last error, or None
retry.last_error      # Diagnostic object, or None
retry.history         # List of AttemptRecord objects
```

### `parse_json`

```python
from handoff import parse_json

# Handles code fences
data = parse_json('```json\n{"key": "value"}\n```')
# Returns: {"key": "value"}

# Handles LLM chattiness
data = parse_json('Sure! Here\'s the JSON:\n{"key": "value"}\nLet me know if you need anything!')
# Returns: {"key": "value"}

# Repairs malformed JSON
data = parse_json('{"a": 1,}')        # trailing comma
data = parse_json("{'a': 1}")         # single quotes
data = parse_json('{a: 1}')           # unquoted keys
data = parse_json('{"a": 1')          # missing brace
data = parse_json('{"a": 1 // comment}')  # JS comments

# Raises ParseError on failure (retryable by @guard)
# ParseError includes detailed context:
#   - Line/column location
#   - Context snippet with pointer
#   - Suggested fix
#   - Input preview for debugging
```

### `HandoffViolation`

Raised when all retry attempts are exhausted:

```python
from handoff import HandoffViolation

try:
    result = my_agent(state)
except HandoffViolation as e:
    print(e.node_name)       # "writer"
    print(e.total_attempts)  # 3
    print(e.history)         # List of AttemptRecord with diagnostics
    print(e.to_dict())       # Serializable for logging
```

### Handle Failures

```python
@guard(output=Schema, on_fail="raise")        # Raise exception (default)
@guard(output=Schema, on_fail="return_none")   # Return None on failure
@guard(output=Schema, on_fail="return_input")  # Return input unchanged
@guard(output=Schema, on_fail=my_handler)      # Custom handler
```

## Examples

| Demo | What it shows |
|------|---------------|
| [`examples/llm_demo`](examples/llm_demo/) | Retry-with-feedback: writer fails, gets feedback, self-corrects |
| [`examples/rag_demo`](examples/rag_demo/) | Multi-stage pipeline validation + hallucinated citation detection |

Both demos support `--api` for real LLM calls and run with mock data by default.

## With LangGraph

```python
from handoff.langgraph import guarded_node
from pydantic import BaseModel, Field

class RouterOutput(BaseModel):
    next_agent: str = Field(pattern="^(writer|reviewer|done)$")
    messages: list

@guarded_node(output=RouterOutput)
def router(state: dict) -> dict:
    return {
        "next_agent": "writer",
        "messages": state["messages"]
    }
```

## Why not just use Pydantic directly?

You should! Handoff uses Pydantic under the hood.

The difference:

| Pydantic alone | Handoff |
|----------------|---------|
| `ValidationError: 1 validation error` | `HandoffViolation in 'router_node'` |
| Generic stack trace | Exact node + field + suggestion |
| You wire up validation manually | One decorator |
| No retry | Automatic retry with feedback |
| Errors are for developers | Errors are actionable for agents |

## Roadmap

- [ ] Invariant contracts (input/output relationships)
- [ ] CrewAI adapter
- [x] Retry with feedback loop
- [ ] VS Code extension for violation inspection

## Contributing

Contributions welcome! Please open an issue first to discuss what you'd like to change.

## License

MIT

---

Built for developers who are tired of debugging agent handoffs.
