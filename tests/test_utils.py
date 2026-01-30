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
