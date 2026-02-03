"""Utility functions for handoff."""

from dataclasses import dataclass
import json
import re
from typing import overload, Literal

from json_repair import loads as repair_json


@dataclass
class ParseResult:
    """Result of parse_json with detailed=True.

    Attributes:
        data: The parsed JSON data (dict or list).
        truncated: True if the input appeared to be truncated (e.g., hit max_tokens).
        repaired: True if the JSON had syntax errors that were auto-fixed.
    """

    data: dict | list
    truncated: bool = False
    repaired: bool = False


def _format_context_snippet(text: str, lineno: int, colno: int) -> str:
    """Format a snippet of text around the error location.

    Shows 1 line before, the error line with pointer, and 1 line after.
    """
    lines = text.splitlines()
    if not lines or lineno < 1:
        return ""

    # Clamp to valid range
    error_idx = min(lineno - 1, len(lines) - 1)
    start_idx = max(0, error_idx - 1)
    end_idx = min(len(lines), error_idx + 2)

    # Calculate width for line numbers
    max_lineno = end_idx
    width = len(str(max_lineno))

    result = []
    for i in range(start_idx, end_idx):
        line_num = i + 1
        line_content = lines[i]
        # Truncate long lines
        if len(line_content) > 80:
            line_content = line_content[:77] + "..."
        result.append(f"  {line_num:>{width}} | {line_content}")

        # Add pointer on error line
        if i == error_idx:
            # Position pointer at column (1-indexed), clamped to truncated line length
            pointer_pos = min(colno - 1, len(line_content)) if colno > 0 else 0
            pointer = " " * pointer_pos + "^"
            result.append(f"  {' ' * width} | {pointer}")

    return "\n".join(result)


def _suggest_fix(error_msg: str, text: str, lineno: int, colno: int) -> str | None:
    """Suggest a fix based on the error message and context."""
    msg_lower = error_msg.lower()

    # Get character at/near error position for context
    lines = text.splitlines()
    char_at_error = ""
    if lines and 1 <= lineno <= len(lines):
        line = lines[lineno - 1]
        if 0 < colno <= len(line):
            char_at_error = line[colno - 1]

    # Pattern match common errors
    if "unterminated string" in msg_lower:
        return "Missing closing quote. Check for unescaped quotes inside the string."

    if "expecting property name" in msg_lower:
        if char_at_error == "}":
            return "Trailing comma before closing brace. Remove the comma."
        return "Object key must be a double-quoted string."

    if "unexpected end" in msg_lower or "end of data" in msg_lower:
        # Count open vs close braces/brackets
        open_braces = text.count("{") - text.count("}")
        open_brackets = text.count("[") - text.count("]")
        if open_braces > 0:
            return f"Missing closing brace. {open_braces} unclosed '{{' found."
        if open_brackets > 0:
            return f"Missing closing bracket. {open_brackets} unclosed '[' found."
        return "Unexpected end of input. Check for missing closing braces or brackets."

    if "expecting value" in msg_lower:
        if char_at_error == ",":
            return "Trailing comma in array. Remove the comma before ']'."
        if char_at_error == "}":
            return "Missing value after colon."
        return "Expected a value (string, number, object, array, true, false, or null)."

    if "expecting ':'" in msg_lower or "expecting colon" in msg_lower:
        return "Missing colon after object key."

    if "expecting ',' or '}'" in msg_lower:
        return "Missing comma between object properties, or extra content after value."

    if "expecting ',' or ']'" in msg_lower:
        return "Missing comma between array elements, or extra content after value."

    if re.search(r"invalid \\escape|invalid escape", msg_lower):
        return "Invalid escape sequence. Use \\\\ for backslash, or \\n, \\t, \\r, \\u for special chars."

    return None


def _format_parse_error(
    error: json.JSONDecodeError, raw_text: str, preview_len: int = 200
) -> str:
    """Format a comprehensive parse error message."""
    parts = [f"JSON parse error: {error.msg} at line {error.lineno}, column {error.colno}"]

    # Add context snippet
    snippet = _format_context_snippet(raw_text, error.lineno, error.colno)
    if snippet:
        parts.append("")
        parts.append(snippet)

    # Add suggestion
    suggestion = _suggest_fix(error.msg, raw_text, error.lineno, error.colno)
    if suggestion:
        parts.append("")
        parts.append(f"Suggestion: {suggestion}")

    # Add input preview
    preview = raw_text[:preview_len]
    if len(raw_text) > preview_len:
        preview += "..."
    # Escape for single-line display
    preview_escaped = preview.replace("\n", "\\n").replace("\t", "\\t")
    parts.append("")
    parts.append(f"Input preview: '{preview_escaped}'")

    return "\n".join(parts)


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


def _is_likely_truncated(text: str) -> bool:
    """Detect if JSON appears to be truncated (e.g., hit max_tokens).

    Returns True if there are unmatched opening braces/brackets,
    indicating the JSON was cut off before completion.
    """
    if not text:
        return False

    # Count unmatched braces/brackets, respecting JSON string boundaries
    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape = False

    for ch in text:
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

        if ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1

    return depth_brace > 0 or depth_bracket > 0


@overload
def parse_json(text: str, *, detailed: Literal[False] = False) -> dict | list: ...


@overload
def parse_json(text: str, *, detailed: Literal[True]) -> ParseResult: ...


def parse_json(text: str, *, detailed: bool = False) -> dict | list | ParseResult:
    """Parse JSON from text, handling common LLM output quirks.

    Strips UTF-8 BOM, markdown code fences, and conversational
    wrappers (preamble/postamble text) before parsing. Repairs
    common JSON malformations (trailing commas, single quotes,
    unquoted keys, missing braces, comments).

    Args:
        text: The text to parse as JSON.
        detailed: If True, return a ParseResult with truncation/repair info.

    Returns:
        The parsed JSON data (dict or list), or ParseResult if detailed=True.

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

    # Track status for detailed mode
    was_repaired = False
    was_truncated = False

    # Check for truncation before any processing
    if _is_likely_truncated(cleaned):
        was_truncated = True

    def _return(data: dict | list) -> dict | list | ParseResult:
        if detailed:
            return ParseResult(data=data, truncated=was_truncated, repaired=was_repaired)
        return data

    # Fast path: try parsing directly
    try:
        return _return(json.loads(cleaned))
    except json.JSONDecodeError as e:
        first_error = e

    # Strip code fences and retry
    stripped = _strip_code_fences(cleaned)
    try:
        return _return(json.loads(stripped))
    except json.JSONDecodeError:
        pass

    # Extract JSON by boundary (handles conversational wrappers)
    extracted = _extract_json_substring(cleaned)
    if extracted is not None:
        try:
            return _return(json.loads(extracted))
        except json.JSONDecodeError:
            pass

    # Attempt repair on extracted JSON or cleaned text
    repair_target = extracted if extracted is not None else cleaned
    try:
        repaired = repair_json(repair_target)
        # Only accept dict/list results (json_repair returns "" for invalid input)
        if isinstance(repaired, (dict, list)):
            was_repaired = True
            return _return(repaired)
    except Exception:
        pass

    raise ParseError(
        _format_parse_error(first_error, text),
        raw_output=text[:500],
        original=first_error,
    )
