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
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def _get_lockfile_path() -> Path:
    """Get a user-specific lockfile path."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "notify-hook.lock"
    return Path(f"/tmp/notify-hook-{os.getuid()}.lock")

LOCKFILE = _get_lockfile_path()
NOTIFY_SERVER = os.environ.get("CLAUDE_NOTIFY_SERVER", "http://localhost:51515")
MIN_DURATION = int(os.environ.get("CLAUDE_NOTIFY_MIN_DURATION", "60"))


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO8601 timestamp."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


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
    except Exception:
        return 0


def get_last_user_message(transcript_path: Path) -> str:
    """Get the last user message from transcript."""
    try:
        lines = transcript_path.read_text().strip().split("\n")
        entries = [json.loads(line) for line in lines if line.strip()]

        user_entries = [
            e for e in entries
            if e.get("type") == "user"
            and isinstance(e.get("message", {}).get("content"), str)
        ]
        if user_entries:
            return user_entries[-1]["message"]["content"][:500]
    except Exception:
        pass
    return ""


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
        last_user_ts = user_entries[-1]["timestamp"]

        # Get all assistant messages after that
        texts = []
        for e in entries:
            if e.get("type") == "assistant" and e.get("timestamp", "") > last_user_ts:
                content = e.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            if text:
                                texts.append(text)
                elif isinstance(content, str):
                    texts.append(content)

        return "\n".join(texts)[:2000]
    except Exception:
        return ""


def get_summary(last_user_msg: str, assistant_msgs: str) -> str:
    """Get a summary using claude --print."""
    if not assistant_msgs:
        return ""

    prompt = f"""Output ONLY a single short sentence (max 15 words) summarizing what was done. No questions, no explanations, no preamble. Just the summary sentence.

User asked: {last_user_msg[:200]}

Assistant did: {assistant_msgs[:1500]}"""

    try:
        LOCKFILE.touch()
        result = subprocess.run(
            ["claude", "--print", "--model", "haiku"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""
    finally:
        LOCKFILE.unlink(missing_ok=True)


def send_notification(message: str) -> None:
    """Send notification to audio-notify-server."""
    try:
        import urllib.request
        from urllib.parse import urlparse

        # Validate URL scheme to prevent SSRF
        parsed = urlparse(NOTIFY_SERVER)
        if parsed.scheme not in ("http", "https"):
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
    except Exception:
        pass


def main():
    # Prevent recursive hook triggers
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

    send_notification(message)


if __name__ == "__main__":
    main()
