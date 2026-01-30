# RAG Demo: Multi-Stage Validation

RAG pipeline with schema validation at every stage and hallucinated citation detection.

## Quick Start

```bash
# Pipeline + hallucination detection (default)
python -m examples.rag_demo.run_demo

# Real LLM calls via OpenRouter
export OPENROUTER_API_KEY=your_key
python -m examples.rag_demo.run_demo --api
```

## The Pipeline

```
Query Parser --> Retriever --> Reranker --> Generator
     |               |             |            |
 ParsedQuery   RetrievedDocs  RankedDocs    RAGOutput
```

Every stage is guarded with `@guard(output=...)`. The generator has `max_attempts=3` for retry support.

After the pipeline completes, `validate_citations()` checks that every cited document was actually retrieved — catching hallucinated sources.

## What the Demo Shows

1. **Multi-stage validation** — Each pipeline stage validates its output schema
2. **Hallucination detection** — `validate_citations` raises `HandoffViolation` when the generator cites `doc_999`, which was never retrieved

## Key Patterns

```python
from handoff import HandoffViolation, ViolationContext

def validate_citations(result, state):
    retrieved_ids = {doc["id"] for doc in state["ranked"]["documents"]}
    cited_ids = {c["doc_id"] for c in result["citations"]}
    hallucinated = cited_ids - retrieved_ids

    if hallucinated:
        raise HandoffViolation(
            context=ViolationContext(
                node_name="generator",
                contract_type="invariant",
                field_path="citations",
                expected=f"Doc IDs from: {retrieved_ids}",
                received=f"Hallucinated: {hallucinated}",
                suggestion="Generator cited documents not in retrieval set",
            )
        )
```

## Schemas

| Stage | Schema | Key Validations |
|-------|--------|-----------------|
| Query Parser | `ParsedQuery` | Non-empty search query |
| Retriever | `RetrievedDocs` | At least 1 document returned |
| Reranker | `RankedDocs` | Scores in [0,1], sorted descending |
| Generator | `RAGOutput` | Answer >= 50 chars, >= 1 citation, confidence in [0,1] |

## Requirements

```bash
pip install handoff-guard

# For --api mode
pip install httpx
export OPENROUTER_API_KEY=your_key
```
