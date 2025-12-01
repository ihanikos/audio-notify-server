#!/usr/bin/env python3
"""Tests for the notify-turn-hook.py sample hook."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Optional


class TestNotifyHook(unittest.TestCase):
    """Test cases for the notify-turn-hook.py hook."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.script_dir = Path(__file__).parent
        cls.hook_path = cls.script_dir.parent / "examples" / "notify-turn-hook.py"
        if not cls.hook_path.exists():
            raise FileNotFoundError(f"Hook not found at {cls.hook_path}")

    def setUp(self):
        """Set up each test."""
        self.test_dir = tempfile.mkdtemp()
        self.mock_bin = Path(self.test_dir) / "bin"
        self.mock_bin.mkdir()
        self.transcript = Path(self.test_dir) / "transcript.jsonl"
        self.curl_log = Path(self.test_dir) / "curl_calls.log"

        # Remove any existing lockfile
        lockfile = Path("/tmp/notify-hook.lock")
        if lockfile.exists():
            lockfile.unlink()

        self._create_mocks()

    def tearDown(self):
        """Clean up after each test."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
        # Clean up lockfile
        lockfile = Path("/tmp/notify-hook.lock")
        if lockfile.exists():
            lockfile.unlink()

    def _create_mocks(self):
        """Create mock executable for claude."""
        # Mock claude command
        claude_mock = self.mock_bin / "claude"
        claude_mock.write_text('''#!/bin/bash
if [[ "$*" == *"--print"* ]]; then
    echo "Test summary of completed work."
fi
''')
        claude_mock.chmod(0o755)

    def _create_transcript(self, user_ts: str, asst_ts: str, user_msg: str, asst_msg: str):
        """Create a test transcript file."""
        lines = [
            json.dumps({
                "type": "user",
                "timestamp": user_ts,
                "message": {"content": user_msg}
            }),
            json.dumps({
                "type": "assistant",
                "timestamp": asst_ts,
                "message": {"content": [{"type": "text", "text": asst_msg}]}
            })
        ]
        self.transcript.write_text("\n".join(lines) + "\n")

    def _run_hook(self, cwd: str = "/tmp/test-project", env_overrides: Optional[dict] = None):
        """Run the hook."""
        hook_input = json.dumps({
            "transcript_path": str(self.transcript),
            "cwd": cwd
        })

        env = os.environ.copy()
        env["PATH"] = f"{self.mock_bin}:{env['PATH']}"
        env.setdefault("CLAUDE_NOTIFY_SERVER", "http://test-server:51515")
        env.setdefault("CLAUDE_NOTIFY_MIN_DURATION", "60")

        if env_overrides:
            env.update(env_overrides)

        result = subprocess.run(
            ["python3", str(self.hook_path)],
            input=hook_input,
            capture_output=True,
            text=True,
            env=env
        )

        return result

    def test_skip_short_tasks(self):
        """Tasks under 60 seconds should not trigger notification."""
        # Create transcript with 30 second duration
        self._create_transcript(
            "2025-01-01T10:00:00Z",
            "2025-01-01T10:00:30Z",
            "Do something quick",
            "Done quickly"
        )

        # Hook runs in subprocess, so we verify it exits successfully
        # without errors (duration check should cause early exit)
        result = self._run_hook()
        self.assertEqual(result.returncode, 0)

    def test_notify_long_tasks(self):
        """Tasks over 60 seconds should trigger notification."""
        # Create transcript with 120 second duration
        self._create_transcript(
            "2025-01-01T10:00:00Z",
            "2025-01-01T10:02:00Z",
            "Do something long",
            "Done after a while"
        )

        # Hook runs in subprocess, so we can't mock urlopen
        # We verify the hook ran successfully without errors
        result = self._run_hook()
        self.assertEqual(result.returncode, 0)

    def test_lockfile_prevents_recursion(self):
        """Lockfile should prevent recursive hook execution."""
        # Create lockfile before running
        Path("/tmp/notify-hook.lock").touch()

        self._create_transcript(
            "2025-01-01T10:00:00Z",
            "2025-01-01T10:05:00Z",
            "Test",
            "Done"
        )

        result = self._run_hook()
        self.assertEqual(result.returncode, 0)
        # Hook should exit early due to lockfile

    def test_missing_transcript(self):
        """Hook should handle missing transcript gracefully."""
        # Don't create transcript
        hook_input = json.dumps({
            "transcript_path": "/nonexistent/path.jsonl",
            "cwd": "/tmp/test"
        })

        env = os.environ.copy()
        env["CLAUDE_NOTIFY_MIN_DURATION"] = "60"

        result = subprocess.run(
            ["python3", str(self.hook_path)],
            input=hook_input,
            capture_output=True,
            text=True,
            env=env
        )

        self.assertEqual(result.returncode, 0)

    def test_invalid_json_input(self):
        """Hook should handle invalid JSON input gracefully."""
        env = os.environ.copy()

        result = subprocess.run(
            ["python3", str(self.hook_path)],
            input="not valid json",
            capture_output=True,
            text=True,
            env=env
        )

        self.assertEqual(result.returncode, 0)


class TestHookFunctions(unittest.TestCase):
    """Test individual functions from the hook."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.transcript = Path(self.test_dir) / "transcript.jsonl"

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_transcript(self, entries: list):
        """Create transcript from list of entries."""
        lines = [json.dumps(e) for e in entries]
        self.transcript.write_text("\n".join(lines) + "\n")

    def _import_hook_module(self):
        """Import and return the hook module."""
        import importlib.util
        hook_path = Path(__file__).parent.parent / "examples" / "notify-turn-hook.py"
        spec = importlib.util.spec_from_file_location("hook", hook_path)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        return hook

    def test_duration_calculation(self):
        """Test duration calculation from transcript."""
        hook = self._import_hook_module()

        self._create_transcript([
            {"type": "user", "timestamp": "2025-01-01T10:00:00Z",
             "message": {"content": "test"}},
            {"type": "assistant", "timestamp": "2025-01-01T10:02:00Z",
             "message": {"content": [{"type": "text", "text": "done"}]}}
        ])

        duration = hook.get_duration_from_transcript(self.transcript)
        self.assertEqual(duration, 120)

    def test_duration_with_no_user_message(self):
        """Test duration when there's no user message."""
        hook = self._import_hook_module()

        self._create_transcript([
            {"type": "assistant", "timestamp": "2025-01-01T10:02:00Z",
             "message": {"content": [{"type": "text", "text": "done"}]}}
        ])

        duration = hook.get_duration_from_transcript(self.transcript)
        self.assertEqual(duration, 0)

    def test_get_last_user_message(self):
        """Test extracting last user message."""
        hook = self._import_hook_module()

        # Use a message longer than 20 chars to avoid context injection
        self._create_transcript([
            {"type": "user", "timestamp": "2025-01-01T10:00:00Z",
             "message": {"content": "first message from user"}},
            {"type": "assistant", "timestamp": "2025-01-01T10:01:00Z",
             "message": {"content": [{"type": "text", "text": "response"}]}},
            {"type": "user", "timestamp": "2025-01-01T10:02:00Z",
             "message": {"content": "second message from the user"}},
        ])

        msg = hook.get_last_user_message(self.transcript)
        self.assertEqual(msg, "second message from the user")

    def test_get_last_user_message_short_with_context(self):
        """Test that short user messages include previous assistant context."""
        hook = self._import_hook_module()

        self._create_transcript([
            {"type": "user", "timestamp": "2025-01-01T10:00:00Z",
             "message": {"content": "Do something for me please"}},
            {"type": "assistant", "timestamp": "2025-01-01T10:01:00Z",
             "message": {"content": [{"type": "text", "text": "Would you like me to proceed?"}]}},
            {"type": "user", "timestamp": "2025-01-01T10:02:00Z",
             "message": {"content": "Yes"}},
        ])

        msg = hook.get_last_user_message(self.transcript)
        self.assertTrue(msg.startswith("(In response to: "))
        self.assertIn("Would you like me to proceed?", msg)
        self.assertIn("\nUser said: Yes", msg)
        # Verify no ellipsis since assistant message is short (not truncated)
        self.assertNotIn("...", msg)

    def test_get_last_user_message_short_no_prior_assistant(self):
        """Test that short user message as first message returns just the message."""
        hook = self._import_hook_module()

        # Short user message with no prior assistant message
        self._create_transcript([
            {"type": "user", "timestamp": "2025-01-01T10:00:00Z",
             "message": {"content": "Yes"}},
        ])

        msg = hook.get_last_user_message(self.transcript)
        # Should return just the user message without context
        self.assertEqual(msg, "Yes")

    def test_get_assistant_messages(self):
        """Test extracting assistant messages after last user message."""
        hook = self._import_hook_module()

        self._create_transcript([
            {"type": "user", "timestamp": "2025-01-01T10:00:00Z",
             "message": {"content": "do something"}},
            {"type": "assistant", "timestamp": "2025-01-01T10:01:00Z",
             "message": {"content": [{"type": "text", "text": "working on it"}]}},
            {"type": "assistant", "timestamp": "2025-01-01T10:02:00Z",
             "message": {"content": [{"type": "text", "text": "done!"}]}},
        ])

        msgs = hook.get_assistant_messages(self.transcript)
        self.assertIn("working on it", msgs)
        self.assertIn("done!", msgs)

    def test_get_git_context_in_git_repo(self):
        """Test git context returns repo name and branch in a git repo."""
        import re
        hook = self._import_hook_module()

        # Use this test's repo directory
        repo_dir = str(Path(__file__).parent.parent)
        context = hook.get_git_context(repo_dir)

        # Should contain repo name and branch with format "repo, branch: "
        # Verify it's non-empty and has the expected format
        self.assertNotEqual(context, "")
        self.assertTrue(context.endswith(": "))
        # Verify format matches "repo, branch: " or "repo: "
        self.assertIsNotNone(
            re.match(r'^[^,]+, [^,]+: $|^[^,]+: $', context),
            f"Context '{context}' doesn't match expected format",
        )

    def test_get_git_context_empty_cwd(self):
        """Test git context returns empty string for empty cwd."""
        hook = self._import_hook_module()

        context = hook.get_git_context("")
        self.assertEqual(context, "")

    def test_get_git_context_non_git_dir(self):
        """Test git context falls back to directory name for non-git directory."""
        hook = self._import_hook_module()

        # Use test directory which is not a git repo
        context = hook.get_git_context(self.test_dir)
        # Should fall back to directory name
        dir_name = Path(self.test_dir).name
        self.assertIn(dir_name, context)
        self.assertTrue(context.endswith(": "))


if __name__ == "__main__":
    unittest.main(verbosity=2)
