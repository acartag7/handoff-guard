# LLM Demo: Retry-with-Feedback

Multi-agent pipeline where the writer fails, gets feedback, and self-corrects.

## Quick Start

```bash
# Retry demo — watch the writer fail and self-correct (default)
python -m examples.llm_demo.run_demo

# Failure demo — all retries exhausted, HandoffViolation with full history
python -m examples.llm_demo.run_demo --failure-demo

# Full pipeline in mock mode
python -m examples.llm_demo.run_demo --pipeline

# Full pipeline with real LLM calls via OpenRouter
export OPENROUTER_API_KEY=your_key
python -m examples.llm_demo.run_demo --pipeline --api
```

## The Pipeline

```
Planner --> Researcher --> Writer
```

Each agent is decorated with `@guard(output=..., max_attempts=3)`. When an agent returns invalid output, the guard:

1. Captures what went wrong (field path, expected vs received)
2. Feeds that back to the agent via `retry.feedback()`
3. Re-calls the agent with the feedback appended to its prompt

## Key Patterns

```python
from handoff import guard, retry, parse_json

@guard(output=WriterOutput, node_name="writer", max_attempts=3)
def writer_agent(state, *, use_llm=False):
    prompt = "Write JSON with: draft, word_count, tone, title."

    if retry.is_retry:
        prompt += f"\n\n{retry.feedback()}"

    if use_llm:
        return parse_json(call_llm(prompt))

    return {...}  # hardcoded valid response
```

## Requirements

```bash
pip install handoff-guard

# For --api mode
pip install httpx
export OPENROUTER_API_KEY=your_key
```
