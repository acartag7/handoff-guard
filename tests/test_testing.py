"""Tests for handoff.testing utilities."""

from handoff.testing import mock_retry
from handoff.retry import retry


class TestMockRetry:

    def test_mock_retry_sets_context(self):
        with mock_retry(attempt=2, max_attempts=3) as state:
            assert state.attempt == 2
            assert state.max_attempts == 3
        # After exit, proxy returns defaults
        assert retry.is_retry is False

    def test_mock_retry_proxy_works(self):
        with mock_retry(attempt=3, max_attempts=5, feedback_text="Fix the output"):
            assert retry.is_retry is True
            assert retry.attempt == 3
            assert retry.max_attempts == 5
            fb = retry.feedback()
            assert fb is not None
            assert "Fix the output" in fb
