"""Tests for handoff.utils."""

import pytest
from handoff.utils import parse_json, ParseError, ParseResult


class TestParseJson:

    def test_parse_json_valid(self):
        result = parse_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_parse_json_code_fence(self):
        text = '```json\n{"key": "value"}\n```'
        result = parse_json(text)
        assert result == {"key": "value"}

    def test_parse_json_invalid(self):
        with pytest.raises(ParseError) as exc_info:
            parse_json("not json at all")
        assert exc_info.value.raw_output is not None

    def test_parse_json_non_string(self):
        with pytest.raises(ParseError):
            parse_json(12345)

    def test_parse_json_bom(self):
        text = '\ufeff{"key": "value"}'
        result = parse_json(text)
        assert result == {"key": "value"}

    # --- Conversational wrapper stripping ---

    def test_preamble_sure(self):
        text = 'Sure! Here is the JSON:\n{"key": "value"}'
        assert parse_json(text) == {"key": "value"}

    def test_preamble_heres_the(self):
        text = "Here's the validation result:\n{\"status\": \"pass\"}"
        assert parse_json(text) == {"status": "pass"}

    def test_preamble_certainly(self):
        text = 'Certainly! I\'ve analyzed the handoff.\n{"score": 10}'
        assert parse_json(text) == {"score": 10}

    def test_postamble_let_me_know(self):
        text = '{"key": "value"}\nLet me know if you need anything else!'
        assert parse_json(text) == {"key": "value"}

    def test_postamble_hope_this_helps(self):
        text = '{"key": "value"}\n\nI hope this helps!'
        assert parse_json(text) == {"key": "value"}

    def test_preamble_and_postamble(self):
        text = (
            "Sure, here you go!\n"
            '{"key": "value"}\n'
            "Let me know if you have questions."
        )
        assert parse_json(text) == {"key": "value"}

    def test_multiline_wrapper(self):
        text = (
            "I've carefully reviewed the handoff document.\n"
            "Here are my findings:\n\n"
            '{"findings": ["a", "b"]}\n\n'
            "Feel free to reach out if you need clarification."
        )
        assert parse_json(text) == {"findings": ["a", "b"]}

    def test_code_fence_with_surrounding_wrapper(self):
        text = (
            "Here is the result:\n"
            "```json\n"
            '{"key": "value"}\n'
            "```\n"
            "Hope that helps!"
        )
        assert parse_json(text) == {"key": "value"}

    def test_preserves_wrapper_like_strings_in_values(self):
        text = (
            "Sure!\n"
            '{"message": "Sure! Here is the JSON. Let me know if you need help."}'
        )
        result = parse_json(text)
        assert result["message"] == "Sure! Here is the JSON. Let me know if you need help."

    def test_array_json_with_wrappers(self):
        text = 'Here you go:\n[1, 2, 3]\nDone!'
        assert parse_json(text) == [1, 2, 3]

    def test_nested_objects_with_wrappers(self):
        text = (
            "Absolutely!\n"
            '{"outer": {"inner": {"deep": true}}}\n'
            "That should cover it."
        )
        assert parse_json(text) == {"outer": {"inner": {"deep": True}}}

    def test_json_with_escaped_quotes_in_strings(self):
        text = 'Here:\n{"msg": "He said \\"hello\\""}  \nEnjoy!'
        assert parse_json(text) == {"msg": 'He said "hello"'}

    # --- JSON repair ---

    def test_parse_json_fixes_trailing_comma_object(self):
        assert parse_json('{"a": 1,}') == {"a": 1}

    def test_parse_json_fixes_trailing_comma_array(self):
        assert parse_json('[1, 2, 3,]') == [1, 2, 3]

    def test_parse_json_fixes_single_quotes(self):
        assert parse_json("{'a': 'hello'}") == {"a": "hello"}

    def test_parse_json_fixes_unquoted_keys(self):
        assert parse_json('{a: 1, b: 2}') == {"a": 1, "b": 2}

    def test_parse_json_fixes_missing_brace(self):
        assert parse_json('{"a": 1') == {"a": 1}

    def test_parse_json_removes_comments(self):
        assert parse_json('{"a": 1 // comment\n}') == {"a": 1}

    def test_parse_error_contains_original_exception(self):
        with pytest.raises(ParseError) as exc_info:
            parse_json("not json at all")
        assert exc_info.value.original is not None
        assert isinstance(exc_info.value.original, Exception)

    # --- Error location and suggestions (HG-3) ---

    def test_parse_error_includes_location(self):
        # Use input that can't be repaired - no JSON structure at all
        with pytest.raises(ParseError) as exc_info:
            parse_json("not json at all")
        msg = str(exc_info.value).lower()
        assert "line" in msg
        assert "column" in msg or "col" in msg

    def test_parse_error_includes_context_snippet(self):
        # Multi-line non-JSON input
        with pytest.raises(ParseError) as exc_info:
            parse_json("first line\nsecond line\nthird line")
        msg = str(exc_info.value)
        # Should show line numbers and pipe separators
        assert " | " in msg
        assert "1 |" in msg

    def test_parse_error_includes_pointer(self):
        with pytest.raises(ParseError) as exc_info:
            parse_json("not json")
        msg = str(exc_info.value)
        # Should have caret pointer
        assert "^" in msg

    def test_parse_error_includes_suggestion(self):
        # "Expecting value" error should give a suggestion
        with pytest.raises(ParseError) as exc_info:
            parse_json("invalid text here")
        msg = str(exc_info.value).lower()
        assert "suggestion" in msg

    def test_parse_error_includes_preview(self):
        with pytest.raises(ParseError) as exc_info:
            parse_json("not valid json")
        msg = str(exc_info.value)
        assert "input preview" in msg.lower()
        assert "not valid json" in msg

    def test_parse_error_preview_truncates_long_input(self):
        # Long non-JSON input that will fail
        long_input = "x" * 300 + " not json"
        with pytest.raises(ParseError) as exc_info:
            parse_json(long_input)
        msg = str(exc_info.value)
        assert "..." in msg  # Should be truncated in preview
        assert exc_info.value.raw_output is not None

    def test_parse_error_multiline_shows_context(self):
        # Multi-line input - error on first line but context shows surrounding
        text = "line one\nline two\nline three"
        with pytest.raises(ParseError) as exc_info:
            parse_json(text)
        msg = str(exc_info.value)
        # Should show the line with pipe separator
        assert "| " in msg
        assert "line one" in msg

    def test_parse_error_extra_data_suggestion(self):
        # Valid JSON followed by extra data - cannot be repaired
        with pytest.raises(ParseError) as exc_info:
            parse_json('123 extra')
        msg = str(exc_info.value).lower()
        # Should have location info
        assert "line" in msg
        assert "column" in msg or "col" in msg

    # --- Detailed mode with truncation/repair detection (HG-13) ---

    def test_detailed_returns_parse_result(self):
        result = parse_json('{"a": 1}', detailed=True)
        assert isinstance(result, ParseResult)
        assert result.data == {"a": 1}
        assert result.truncated is False
        assert result.repaired is False

    def test_detailed_false_returns_data_directly(self):
        result = parse_json('{"a": 1}', detailed=False)
        assert result == {"a": 1}
        assert not isinstance(result, ParseResult)

    def test_detailed_detects_truncation_missing_brace(self):
        # Simulates max_tokens cutoff mid-object
        text = '{"draft": "This is a long article about technology'
        result = parse_json(text, detailed=True)
        assert result.truncated is True
        assert result.repaired is True  # json_repair fixes it
        assert result.data == {"draft": "This is a long article about technology"}

    def test_detailed_detects_truncation_missing_bracket(self):
        # Simulates max_tokens cutoff mid-array
        text = '{"items": [1, 2, 3, 4, 5'
        result = parse_json(text, detailed=True)
        assert result.truncated is True
        assert result.repaired is True
        assert result.data == {"items": [1, 2, 3, 4, 5]}

    def test_detailed_detects_truncation_nested(self):
        # Deeply nested structure cut off
        text = '{"a": {"b": {"c": "value'
        result = parse_json(text, detailed=True)
        assert result.truncated is True
        assert result.repaired is True

    def test_detailed_detects_repair_trailing_comma(self):
        # Trailing comma needs repair but is not truncation
        text = '{"a": 1, "b": 2,}'
        result = parse_json(text, detailed=True)
        assert result.truncated is False  # Balanced braces
        assert result.repaired is True
        assert result.data == {"a": 1, "b": 2}

    def test_detailed_detects_repair_single_quotes(self):
        text = "{'a': 'hello'}"
        result = parse_json(text, detailed=True)
        assert result.truncated is False
        assert result.repaired is True
        assert result.data == {"a": "hello"}

    def test_detailed_valid_json_no_flags(self):
        # Valid JSON should have both flags as False
        text = '{"valid": true, "count": 42}'
        result = parse_json(text, detailed=True)
        assert result.truncated is False
        assert result.repaired is False
        assert result.data == {"valid": True, "count": 42}

    def test_detailed_with_wrappers_no_repair(self):
        # Conversational wrappers don't count as repair
        text = 'Sure! Here is the JSON:\n{"a": 1}'
        result = parse_json(text, detailed=True)
        assert result.truncated is False
        assert result.repaired is False  # Extraction != repair
        assert result.data == {"a": 1}

    def test_detailed_truncated_with_wrappers(self):
        # Truncated JSON inside wrappers
        text = 'Here you go:\n{"items": [1, 2, 3'
        result = parse_json(text, detailed=True)
        assert result.truncated is True
        assert result.repaired is True
