"""Utility functions for handoff."""

import json


class ParseError(Exception):
    """Raised when output cannot be parsed as JSON."""

    def __init__(self, message: str, raw_output: str | None = None):
        self.raw_output = raw_output
        super().__init__(message)


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from text."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n", 1)
        body = lines[1] if len(lines) > 1 else ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[: -len("```")]
        stripped = body.strip()
    return stripped


def _extract_json_substring(text: str) -> str | None:
    """Extract the outermost JSON object or array from text.

    Finds the first ``{`` or ``[``, then tracks depth (respecting
    JSON string escaping) to locate the matching closer.
    Returns the substring or ``None`` if no valid boundary is found.
    """
    # Find the first JSON opener
    start = None
    opener = None
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            start = i
            opener = ch
            break

    if start is None:
        return None

    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            if in_string:
                escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def parse_json(text: str) -> dict:
    """Parse JSON from text, handling common LLM output quirks.

    Strips UTF-8 BOM, markdown code fences, and conversational
    wrappers (preamble/postamble text) before parsing.

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

    # Fast path: try parsing directly
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strip code fences and retry
    stripped = _strip_code_fences(cleaned)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Extract JSON by boundary (handles conversational wrappers)
    extracted = _extract_json_substring(cleaned)
    if extracted is not None:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

    raise ParseError(
        "Failed to parse JSON: no valid JSON found in text",
        raw_output=text[:500],
    )
