"""Tests for handoff.utils."""

import pytest
from handoff.utils import parse_json, ParseError


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
