"""Utility functions for handoff."""

import json

from json_repair import loads as repair_json


class ParseError(Exception):
    """Raised when output cannot be parsed as JSON."""

    def __init__(
        self,
        message: str,
        raw_output: str | None = None,
        original: Exception | None = None,
    ):
        self.raw_output = raw_output
        self.original = original
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
    wrappers (preamble/postamble text) before parsing. Repairs
    common JSON malformations (trailing commas, single quotes,
    unquoted keys, missing braces, comments).

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

    # Track first decode error for actionable feedback
    first_error: json.JSONDecodeError | None = None

    # Fast path: try parsing directly
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        first_error = e

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

    # Attempt repair on extracted JSON or cleaned text
    repair_target = extracted if extracted is not None else cleaned
    try:
        repaired = repair_json(repair_target)
        # Only accept dict/list results (json_repair returns "" for invalid input)
        if isinstance(repaired, (dict, list)):
            return repaired
    except Exception:
        pass

    raise ParseError(
        f"Invalid JSON: {first_error.msg} at line {first_error.lineno} col {first_error.colno}",
        raw_output=text[:500],
        original=first_error,
    )
