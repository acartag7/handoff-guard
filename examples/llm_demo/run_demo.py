#!/usr/bin/env python3
"""
Demo: handoff-guard with retry-with-feedback.

Run:
    python -m examples.llm_demo.run_demo                # retry demo (default)
    python -m examples.llm_demo.run_demo --failure-demo  # all retries exhausted
    python -m examples.llm_demo.run_demo --pipeline      # full pipeline (mock)
    python -m examples.llm_demo.run_demo --pipeline --api # full pipeline (real LLM)
"""

import argparse

from handoff import HandoffViolation
from . import agents
from .agents import planner_agent, researcher_agent, writer_agent


def print_header(text: str):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def run_pipeline(user_request: str, *, use_llm: bool = False):
    """Run the full Planner -> Researcher -> Writer pipeline."""
    print_header("Pipeline: Planner -> Researcher -> Writer")
    print(f"  Request: {user_request}")
    print(f"  Mode: {'API (real LLM)' if use_llm else 'Mock (hardcoded)'}")
    print()

    state = {"user_request": user_request}

    try:
        print("  [1/3] Planner...")
        plan = planner_agent(state, use_llm=use_llm)
        state["plan"] = plan
        print(f"        Topic: {plan['topic']}")
        print(f"        Questions: {len(plan['questions'])}")

        print("  [2/3] Researcher...")
        research = researcher_agent(state, use_llm=use_llm)
        state["research"] = research
        print(f"        Facts: {len(research['facts'])}")
        print(f"        Sources: {len(research['sources'])}")

        print("  [3/3] Writer...")
        output = writer_agent(state, use_llm=use_llm)
        print(f"        Title: {output['title']}")
        print(f"        Word count: {output['word_count']}")

        print()
        print("  " + "-" * 50)
        print(f"  Title: {output['title']}")
        print(f"  Draft: {output['draft'][:120]}...")
        print("  " + "-" * 50)
        print("\n  Pipeline completed successfully.")

    except HandoffViolation as e:
        print()
        print(f"  Pipeline failed at '{e.node_name}' (attempt {e.total_attempts})")
        print(f"    Field: {e.context.field_path}")
        print(f"    Expected: {e.context.expected}")
        print(f"    Suggestion: {e.context.suggestion}")


def run_retry_demo():
    """Demonstrate retry-with-feedback: writer fails twice, then succeeds."""
    print_header("Retry Demo: Writer self-corrects")
    print("  The writer gets 3 chances. Watch it fail, get feedback, and fix itself:")
    print()

    state = {
        "user_request": "Write about AI agents",
        "plan": {"topic": "AI Agents", "tone": "technical", "questions": ["What?"]},
        "research": {
            "topic": "AI Agents",
            "facts": ["Agents can perform tasks autonomously."],
            "sources": ["arxiv.org"],
            "questions_answered": 1,
        },
    }

    agents._mock_responses["writer"] = [
        # Attempt 1: missing fields (word_count, tone, title)
        {"draft": "AI agents are software programs that can perform tasks autonomously using large language models."},
        # Attempt 2: draft too short (< 100 chars)
        {
            "draft": "AI agents are interesting.",
            "word_count": 5,
            "tone": "technical",
            "title": "AI Agents",
        },
        # Attempt 3: valid
        {
            "draft": (
                "AI agents represent a significant advancement in software engineering, enabling autonomous "
                "multi-step task execution powered by large language models. These agents can plan, research, "
                "and produce content with minimal human intervention."
            ),
            "word_count": 55,
            "tone": "technical",
            "title": "Understanding AI Agents",
        },
    ]

    try:
        result = writer_agent(state)
        print(f"  Attempt {agents._current_attempt}/{3}: \u2705 Valid")
        print()
        print(f"  Writer succeeded after {agents._current_attempt} attempts!")
        print(f"    Title: {result['title']}")
        print(f"    Word count: {result['word_count']}")
        print(f"    Draft: {result['draft'][:100]}...")
    except HandoffViolation as e:
        print(f"  Unexpected failure: {e}")
    finally:
        agents._mock_responses.clear()


def run_failure_demo():
    """Demonstrate exhausted retries: all attempts fail, HandoffViolation raised."""
    print_header("Failure Demo: All retries exhausted")
    print("  The writer returns invalid output 3 times. After all retries,")
    print("  HandoffViolation is raised with the full attempt history:")
    print()

    state = {
        "user_request": "Write about AI agents",
        "plan": {"topic": "AI Agents", "tone": "technical", "questions": ["What?"]},
        "research": {
            "topic": "AI Agents",
            "facts": ["Agents can perform tasks."],
            "sources": ["arxiv.org"],
            "questions_answered": 1,
        },
    }

    agents._mock_responses["writer"] = [
        {"draft": "Too short."},
        {"draft": "Still too short."},
        {"draft": "Not enough content here."},
    ]

    try:
        writer_agent(state)
        print("  Unexpected success!")
    except HandoffViolation as e:
        # Print the last attempt's failure (not printed by _log_attempt since there's no retry after it)
        err = e.history[-1].diagnostic
        if err:
            detail = err.errors[0] if err.errors else err.message
            print(f"  Attempt {e.total_attempts}/{e.total_attempts}: \u274c {detail}")
        print()
        print(f"  HandoffViolation raised after {e.total_attempts} attempts:")
        print(f"    Node: {e.node_name}")
        print(f"    Field: {e.context.field_path}")
        print(f"    Expected: {e.context.expected}")
        print(f"    Suggestion: {e.context.suggestion}")
        print()
        print(f"  Retry history ({len(e.history)} attempts):")
        for record in e.history:
            status = "failed" if record.diagnostic else "succeeded"
            cause = f" ({record.diagnostic.cause})" if record.diagnostic else ""
            print(f"    Attempt {record.attempt}: {status}{cause}")
    finally:
        agents._mock_responses.clear()


def main():
    parser = argparse.ArgumentParser(description="handoff-guard LLM demo")
    parser.add_argument("--pipeline", action="store_true", help="Run the full mock pipeline (Planner -> Researcher -> Writer)")
    parser.add_argument("--api", action="store_true", help="Use real LLM calls via OpenRouter (with --pipeline)")
    parser.add_argument("--request", type=str, default="Write about AI agents", help="User request (with --pipeline)")
    parser.add_argument("--failure-demo", action="store_true", help="Run the exhausted-retries demo")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  HANDOFF-GUARD: LLM Demo")
    print("  Retry-with-feedback at agent boundaries")
    print("=" * 60)

    if args.pipeline:
        run_pipeline(args.request, use_llm=args.api)
    elif args.failure_demo:
        run_failure_demo()
    else:
        run_retry_demo()


if __name__ == "__main__":
    main()
