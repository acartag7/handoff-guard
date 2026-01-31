#!/usr/bin/env python3
"""
Demo: handoff-guard for RAG pipelines.

Showcases multi-stage pipeline validation and citation hallucination detection.

Run:
    python -m examples.rag_demo.run_demo         # pipeline + hallucination check (default)
    python -m examples.rag_demo.run_demo --api    # real LLM calls (needs OPENROUTER_API_KEY)
"""

import argparse

from handoff import HandoffViolation
from .pipeline import (
    query_parser,
    retriever,
    reranker,
    generator,
    validate_citations,
)


def print_header(text: str):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def run_pipeline(query: str, *, use_llm: bool = False):
    """Run the full Parser -> Retriever -> Reranker -> Generator pipeline."""
    print_header("Pipeline: Parser -> Retriever -> Reranker -> Generator")
    print(f"  Query: {query}")
    print(f"  Mode: {'API (real LLM)' if use_llm else 'Mock (hardcoded)'}")
    print()

    state = {"user_query": query}

    try:
        print("  [1/4] Query Parser...")
        parsed = query_parser(state)
        state["parsed_query"] = parsed
        print("        \u2705 ParsedQuery validated")
        print(f"        Search query: '{parsed['search_query']}'")

        print("  [2/4] Retriever...")
        retrieved = retriever(state)
        state["retrieved"] = retrieved
        print(
            f"        \u2705 RetrievedDocs validated ({len(retrieved['documents'])} docs)"
        )

        print("  [3/4] Reranker...")
        ranked = reranker(state)
        state["ranked"] = ranked
        print(
            f"        \u2705 RankedDocs validated (top score: {ranked['documents'][0]['score']:.2f})"
        )

        print("  [4/4] Generator...")
        output = generator(state, use_llm=use_llm)
        print(f"        \u2705 RAGOutput validated ({len(output['answer'])} chars)")

        # Post-pipeline: citation validation
        print()
        print("  Citation check...")
        validate_citations(output, state)
        print(
            f"        \u2705 All {len(output['citations'])} citation(s) reference retrieved docs"
        )

        print()
        print("  " + "-" * 50)
        print(f"  Answer: {output['answer'][:120]}...")
        print(f"  Citations: {len(output['citations'])}")
        print(f"  Confidence: {output['confidence']:.2f}")
        print("  " + "-" * 50)
        print("\n  Pipeline completed successfully.")

    except HandoffViolation as e:
        print()
        print(f"  \u274c Pipeline failed at '{e.node_name}'")
        print(f"    Contract: {e.context.contract_type}")
        print(f"    Field: {e.context.field_path}")
        print(f"    Expected: {e.context.expected}")
        print(f"    Suggestion: {e.context.suggestion}")


def run_hallucination_demo():
    """Show validate_citations catching a hallucinated citation."""
    print_header("Hallucination Detection")
    print("  The generator cites doc_999, which was never retrieved.")
    print("  validate_citations catches this as an invariant violation:")
    print()

    state = {
        "ranked": {
            "documents": [
                {"id": "doc_1", "content": "Python is...", "score": 0.9, "rank": 1},
                {"id": "doc_2", "content": "ML is...", "score": 0.8, "rank": 2},
            ]
        },
    }

    # Simulated generator output with a hallucinated citation
    generator_output = {
        "answer": "Machine learning is a powerful technology that enables computers to learn from data without explicit programming.",
        "citations": [
            {
                "doc_id": "doc_1",
                "quote": "Python is a high-level language",
                "relevance": "Valid",
            },
            {
                "doc_id": "doc_999",
                "quote": "This doc does not exist",
                "relevance": "Hallucinated",
            },
        ],
        "confidence": 0.85,
        "sources_used": 2,
    }

    try:
        validate_citations(generator_output, state)
        print("  No hallucination detected.")
    except HandoffViolation as e:
        print("  \u274c HandoffViolation: hallucinated citation detected")
        print(f"    Contract: {e.context.contract_type}")
        print(f"    Field: {e.context.field_path}")
        print(f"    Expected: {e.context.expected}")
        print(f"    Received: {e.context.received}")
        print(f"    Suggestion: {e.context.suggestion}")
        print()
        print("  This catches a common RAG failure: the generator cites")
        print("  documents that were never retrieved, fabricating sources.")


def main():
    parser = argparse.ArgumentParser(description="handoff-guard RAG demo")
    parser.add_argument(
        "--api", action="store_true", help="Use real LLM calls via OpenRouter"
    )
    parser.add_argument(
        "--query",
        type=str,
        default="What is RAG and why does it reduce hallucinations?",
        help="User query",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  HANDOFF-GUARD: RAG Pipeline Demo")
    print("  Multi-stage validation + hallucination detection")
    print("=" * 60)

    run_pipeline(args.query, use_llm=args.api)
    run_hallucination_demo()


if __name__ == "__main__":
    main()
