"""Configuration management for audio-notify-server."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path("/etc/audio-notify-server/config.json")
DEFAULT_MAX_MESSAGE_LENGTH = 500


def load_config() -> dict:
    """Load configuration from /etc/audio-notify-server/config.json."""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def get_max_message_length() -> int:
    """Get the maximum allowed message length from config."""
    config = load_config()
    return config.get("max_message_length", DEFAULT_MAX_MESSAGE_LENGTH)
