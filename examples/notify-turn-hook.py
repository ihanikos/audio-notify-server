#!/usr/bin/env python3
"""
Sample Stop hook for Claude Code - notifies audio-notify-server when Claude finishes.

Installation:
  1. Copy this file to ~/.claude/hooks/notify-turn.py
  2. chmod +x ~/.claude/hooks/notify-turn.py
  3. Add to ~/.claude/settings.json:
     {
       "hooks": {
         "Stop": [
           {
             "type": "command",
             "command": "~/.claude/hooks/notify-turn.py",
             "timeout": 120
           }
         ]
       }
     }

Configuration (via environment variables):
  CLAUDE_NOTIFY_SERVER - URL of the audio-notify-server (default: http://localhost:51515)
  CLAUDE_NOTIFY_MIN_DURATION - Minimum task duration in seconds to trigger notification (default: 60)

This hook summarizes what was done using claude --print and sends
a spoken notification via audio-notify-server. Only triggers for
tasks that take longer than MIN_DURATION seconds.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

def _get_lockfile_path() -> Path:
    """Get a user-specific lockfile path."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "notify-hook.lock"
    return Path(tempfile.gettempdir()) / f"notify-hook-{os.getuid()}.lock"

LOCKFILE = _get_lockfile_path()
NOTIFY_SERVER = os.environ.get("CLAUDE_NOTIFY_SERVER", "http://localhost:51515")
try:
    MIN_DURATION = int(os.environ.get("CLAUDE_NOTIFY_MIN_DURATION", "60"))
except ValueError:
    MIN_DURATION = 60
DEBUG = os.environ.get("CLAUDE_NOTIFY_DEBUG", "").lower() in ("1", "true")

# Message length thresholds
SHORT_MESSAGE_THRESHOLD = 20  # Include assistant context for messages shorter than this
USER_MESSAGE_LIMIT = 500  # Truncate user messages to this length
ASSISTANT_CONTEXT_LIMIT = 300  # Truncate assistant context to this length
ASSISTANT_MESSAGES_LIMIT = 2000  # Truncate combined assistant messages to this length
# Prompt snippet limits for summarizer
PROMPT_USER_SNIPPET_LIMIT = 200  # User message snippet in summary prompt
PROMPT_ASSISTANT_SNIPPET_LIMIT = 1500  # Assistant message snippet in summary prompt


def _acquire_lock() -> bool:
    """Try to acquire the lock atomically. Returns False if already held."""
    try:
        fd = os.open(LOCKFILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        return False
    except OSError:
        return False
    else:
        return True


def _release_lock() -> None:
    """Release the lock file."""
    try:
        LOCKFILE.unlink()
    except FileNotFoundError:
        pass


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO8601 timestamp."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _extract_assistant_text(entry: dict) -> str:
    """Extract concatenated text content from an assistant message entry."""
    content = entry.get("message", {}).get("content", [])
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text") or ""
                if text:
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    if isinstance(content, str):
        return content
    return ""


def get_duration_from_transcript(transcript_path: Path) -> int:
    """Calculate duration in seconds from transcript."""
    try:
        lines = transcript_path.read_text().strip().split("\n")
        entries = [json.loads(line) for line in lines if line.strip()]

        # Find last user message with string content
        user_entries = [
            e for e in entries
            if e.get("type") == "user"
            and isinstance(e.get("message", {}).get("content"), str)
        ]
        if not user_entries:
            return 0
        last_user = user_entries[-1]

        # Find last assistant message
        asst_entries = [e for e in entries if e.get("type") == "assistant"]
        if not asst_entries:
            return 0
        last_asst = asst_entries[-1]

        user_ts = parse_timestamp(last_user["timestamp"])
        asst_ts = parse_timestamp(last_asst["timestamp"])

        return int((asst_ts - user_ts).total_seconds())
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
        if DEBUG:
            print(f"Debug: get_duration_from_transcript error: {e}", file=sys.stderr)
        return 0


def get_last_user_message(transcript_path: Path) -> str:
    """Get the last user message from transcript.

    If the user message is very short (e.g., "Yes", "ok"), also include
    the previous assistant message for context.
    """
    try:
        lines = transcript_path.read_text().strip().split("\n")
        entries = [json.loads(line) for line in lines if line.strip()]

        user_entries = [
            e for e in entries
            if e.get("type") == "user"
            and isinstance(e.get("message", {}).get("content"), str)
        ]
        if not user_entries:
            return ""

        last_user_msg = user_entries[-1]["message"]["content"].strip()[:USER_MESSAGE_LIMIT]

        # If user message is very short, include previous assistant context
        if len(last_user_msg) < SHORT_MESSAGE_THRESHOLD:
            last_user_ts = parse_timestamp(user_entries[-1]["timestamp"])
            # Find assistant message just before the last user message
            prev_assistant_text = ""
            ellipsis = ""
            for e in reversed(entries):
                entry_ts_str = e.get("timestamp", "")
                if not entry_ts_str:
                    continue
                try:
                    entry_ts = parse_timestamp(entry_ts_str)
                except ValueError:
                    continue
                if entry_ts >= last_user_ts:
                    continue
                if e.get("type") == "assistant":
                    full_text = _extract_assistant_text(e)
                    if full_text:
                        truncated = len(full_text) > ASSISTANT_CONTEXT_LIMIT
                        prev_assistant_text = full_text[:ASSISTANT_CONTEXT_LIMIT]
                        ellipsis = "..." if truncated else ""
                        break  # Only break when we found non-empty text
            if prev_assistant_text:
                return f"(In response to: {prev_assistant_text}{ellipsis})\nUser said: {last_user_msg}"
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
        if DEBUG:
            print(f"Debug: get_last_user_message error: {e}", file=sys.stderr)
        return ""
    else:
        return last_user_msg


def get_assistant_messages(transcript_path: Path) -> str:
    """Get assistant messages after the last user message."""
    try:
        lines = transcript_path.read_text().strip().split("\n")
        entries = [json.loads(line) for line in lines if line.strip()]

        # Find last user message timestamp
        user_entries = [
            e for e in entries
            if e.get("type") == "user"
            and isinstance(e.get("message", {}).get("content"), str)
        ]
        if not user_entries:
            return ""
        last_user_ts = parse_timestamp(user_entries[-1]["timestamp"])

        # Get all assistant messages after that
        texts = []
        for e in entries:
            if e.get("type") != "assistant":
                continue
            entry_ts_str = e.get("timestamp", "")
            if not entry_ts_str:
                continue
            try:
                entry_ts = parse_timestamp(entry_ts_str)
            except ValueError:
                continue
            if entry_ts > last_user_ts:
                text = _extract_assistant_text(e)
                if text:
                    texts.append(text)

        return "\n".join(texts)[:ASSISTANT_MESSAGES_LIMIT]
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
        if DEBUG:
            print(f"Debug: get_assistant_messages error: {e}", file=sys.stderr)
        return ""


def get_summary(last_user_msg: str, assistant_msgs: str) -> str:
    """Get a summary using claude --print."""
    if not assistant_msgs:
        return ""

    prompt = f"""Output ONLY a single short sentence (max 15 words) summarizing what was done. No questions, no explanations, no preamble. Just the summary sentence.

User asked: {last_user_msg[:PROMPT_USER_SNIPPET_LIMIT]}

Assistant did: {assistant_msgs[:PROMPT_ASSISTANT_SNIPPET_LIMIT]}"""

    try:
        if not _acquire_lock():
            return ""
        result = subprocess.run(
            ["claude", "--print", "--model", "haiku"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception as e:
        if DEBUG:
            print(f"Debug: get_summary error: {e}", file=sys.stderr)
        return ""
    finally:
        _release_lock()


def get_git_context(cwd: str) -> str:
    """Get git repo name and branch for notification prefix.

    Returns a string like "repo-name, branch:" or empty string if not a git repo.
    """
    if not cwd:
        return ""

    # Get full path to git executable for security (avoids S607)
    git_path = shutil.which("git")
    if not git_path:
        return ""

    try:
        # Get repo name from remote origin or directory name
        result = subprocess.run(
            [git_path, "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Extract repo name from URL (handles both HTTPS and SSH)
            url = result.stdout.strip()
            repo_name = url.rstrip("/").split("/")[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
        else:
            # Fall back to directory name
            repo_name = Path(cwd).name

        # Get current branch name
        result = subprocess.run(
            [git_path, "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        branch = result.stdout.strip() if result.returncode == 0 else ""

        if repo_name and branch:
            return f"{repo_name}, {branch}: "
        if repo_name:
            return f"{repo_name}: "
    except (OSError, subprocess.TimeoutExpired) as e:
        if DEBUG:
            print(f"Debug: get_git_context error: {e}", file=sys.stderr)
    return ""


def send_notification(message: str) -> None:
    """Send notification to audio-notify-server."""
    try:
        import urllib.request
        from urllib.parse import urlparse

        # Validate URL scheme to prevent SSRF
        parsed = urlparse(NOTIFY_SERVER)
        if parsed.scheme not in ("http", "https"):
            print(f"Warning: Invalid URL scheme '{parsed.scheme}' in CLAUDE_NOTIFY_SERVER", file=sys.stderr)
            return

        data = json.dumps({
            "message": message,
            "speak": True,
            "sound": True
        }).encode()
        req = urllib.request.Request(
            f"{NOTIFY_SERVER}/notify",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=60)
    except Exception as e:
        if DEBUG:
            print(f"Debug: send_notification error: {e}", file=sys.stderr)


def main():
    # Prevent recursive hook triggers (lockfile created atomically by get_summary)
    if LOCKFILE.exists():
        return

    # Read hook input from stdin
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        return

    transcript_path = hook_input.get("transcript_path")
    cwd = hook_input.get("cwd", "")

    if not transcript_path:
        return

    transcript_path = Path(transcript_path)
    if not transcript_path.exists():
        return

    # Check duration
    duration = get_duration_from_transcript(transcript_path)
    if duration < MIN_DURATION:
        return

    # Get git context prefix (repo name and branch)
    prefix = get_git_context(cwd)

    # Build message
    project_name = Path(cwd).name if cwd else "unknown"
    message = f"Your turn in {project_name}"

    # Try to get a summary
    last_user_msg = get_last_user_message(transcript_path)
    assistant_msgs = get_assistant_messages(transcript_path)

    if assistant_msgs:
        summary = get_summary(last_user_msg, assistant_msgs)
        if summary:
            message = summary

    # Prepend prefix to message
    send_notification(f"{prefix}{message}")


if __name__ == "__main__":
    main()
