"""RAG pipeline stages with handoff-guard validation."""

import os

from handoff import guard, retry, parse_json, HandoffViolation, ViolationContext
from .schemas import (
    ParsedQuery,
    Document,
    RetrievedDocs,
    RankedDocs,
    RAGOutput,
)


OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"


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


# Fake document store
DOCUMENT_STORE = {
    "doc_1": {
        "id": "doc_1",
        "content": "Python is a high-level programming language known for its readability and versatility. It was created by Guido van Rossum and first released in 1991.",
        "metadata": {"source": "wikipedia", "year": 2024},
    },
    "doc_2": {
        "id": "doc_2",
        "content": "Machine learning is a subset of artificial intelligence that enables systems to learn from data. Popular frameworks include TensorFlow, PyTorch, and scikit-learn.",
        "metadata": {"source": "textbook", "year": 2023},
    },
    "doc_3": {
        "id": "doc_3",
        "content": "RAG (Retrieval-Augmented Generation) combines retrieval systems with language models to ground responses in factual documents, reducing hallucinations.",
        "metadata": {"source": "research_paper", "year": 2024},
    },
}


@guard(output=ParsedQuery, node_name="query_parser")
def query_parser(state: dict) -> dict:
    """Parse and validate user query."""
    query = state.get("user_query", "")
    return {
        "original_query": query,
        "search_query": query.lower().strip(),
        "filters": {},
        "max_results": 10,
    }


@guard(output=RetrievedDocs, node_name="retriever")
def retriever(state: dict) -> dict:
    """Retrieve documents with validation."""
    query = state["parsed_query"]["search_query"]

    docs = [Document(**doc) for doc in list(DOCUMENT_STORE.values())[:3]]

    return {
        "query": query,
        "documents": [d.model_dump() for d in docs],
        "total_found": len(docs),
    }


@guard(output=RankedDocs, node_name="reranker")
def reranker(state: dict) -> dict:
    """Rerank with validation."""
    docs = state["retrieved"]["documents"]
    query = state["retrieved"]["query"]

    ranked = []
    for i, doc in enumerate(docs):
        ranked.append({
            "id": doc["id"],
            "content": doc["content"],
            "score": 0.9 - (i * 0.1),
            "rank": i + 1,
        })

    return {
        "query": query,
        "documents": ranked,
        "model_used": "cross-encoder/ms-marco",
    }


@guard(output=RAGOutput, node_name="generator", max_attempts=3)
def generator(state: dict, *, use_llm: bool = False) -> dict:
    """Generate answer with validation and retry support."""
    ranked_docs = state["ranked"]["documents"]
    query = state["parsed_query"]["original_query"]
    top_doc = ranked_docs[0]

    prompt = f"""You are a RAG answer generator.
Output ONLY valid JSON with this structure:
{{"answer": "...", "citations": [{{"doc_id": "...", "quote": "...", "relevance": "..."}}], "confidence": 0.0-1.0, "sources_used": N}}

The answer must be at least 50 characters. Include at least 1 citation with a quote of at least 5 characters.
Only cite documents from this set: {[d['id'] for d in ranked_docs]}

Query: {query}
Documents:
{chr(10).join(f'- {d["id"]}: {d["content"][:100]}' for d in ranked_docs)}"""

    if retry.is_retry:
        prompt += f"\n\n{retry.feedback()}"

    if use_llm:
        response = call_llm([
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ])
        return parse_json(response)

    return {
        "answer": f"Based on the retrieved documents about your query '{query}': {top_doc['content']}",
        "citations": [
            {
                "doc_id": top_doc["id"],
                "quote": top_doc["content"][:50],
                "relevance": "Directly answers the query",
            }
        ],
        "confidence": top_doc["score"],
        "sources_used": 1,
    }


def validate_citations(result: dict, state: dict) -> dict:
    """Ensure cited doc IDs exist in retrieved docs. Catches hallucinated citations."""
    retrieved_ids = {doc["id"] for doc in state.get("ranked", {}).get("documents", [])}
    cited_ids = {c["doc_id"] for c in result.get("citations", [])}

    hallucinated = cited_ids - retrieved_ids

    if hallucinated:
        raise HandoffViolation(
            context=ViolationContext(
                node_name="generator",
                contract_type="invariant",
                field_path="citations",
                expected=f"Doc IDs from retrieved set: {retrieved_ids}",
                received=f"Hallucinated doc IDs: {hallucinated}",
                received_type="set",
                suggestion="Generator cited documents not in retrieval set - check for hallucination",
            )
        )

    return result
