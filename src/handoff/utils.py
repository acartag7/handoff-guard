"""Utility functions for handoff."""

import json


class ParseError(Exception):
    """Raised when output cannot be parsed as JSON."""

    def __init__(self, message: str, raw_output: str | None = None):
        self.raw_output = raw_output
        super().__init__(message)


def parse_json(text: str) -> dict:
    """Parse JSON from text, handling common LLM output quirks.

    Strips UTF-8 BOM and markdown code fences before parsing.

    Raises:
        ParseError: If text cannot be parsed as JSON.
    """
    if not isinstance(text, str):
        raise ParseError(
            f"Expected string, got {type(text).__name__}",
            raw_output=repr(text)[:500],
        )

    # Strip UTF-8 BOM
    cleaned = text.lstrip("\ufeff")

    # Strip markdown code fences
    stripped = cleaned.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n", 1)
        if len(lines) > 1:
            body = lines[1]
        else:
            body = ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[: -len("```")]
        stripped = body.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ParseError(
            f"Failed to parse JSON: {e}",
            raw_output=text[:500],
        ) from e
