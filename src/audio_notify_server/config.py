"""Configuration management for audio-notify-server."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# Config file locations (checked in order, first found wins)
USER_CONFIG_PATH = Path.home() / ".config" / "audio-notify-server" / "config.json"
SYSTEM_CONFIG_PATH = Path("/etc/audio-notify-server/config.json")

DEFAULT_MAX_MESSAGE_LENGTH = 500

# ElevenLabs defaults
DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel" voice
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"


@dataclass
class ElevenLabsConfig:
    """ElevenLabs TTS configuration."""

    enabled: bool
    api_key: str | None
    voice_id: str
    model_id: str


def load_config() -> dict:
    """Load configuration from config file.

    Checks in order:
    1. ~/.config/audio-notify-server/config.json (user config)
    2. /etc/audio-notify-server/config.json (system config)

    Returns:
        Configuration dictionary, or empty dict if no config found.

    """
    for config_path in (USER_CONFIG_PATH, SYSTEM_CONFIG_PATH):
        if config_path.exists():
            try:
                return json.loads(config_path.read_text())
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON in config file {}: {}", config_path, e)
            except OSError as e:
                logger.error("Failed to read config file {}: {}", config_path, e)
    return {}


def get_max_message_length() -> int:
    """Get the maximum allowed message length from config."""
    config = load_config()
    return config.get("max_message_length", DEFAULT_MAX_MESSAGE_LENGTH)


def get_elevenlabs_config() -> ElevenLabsConfig:
    """Get ElevenLabs TTS configuration.

    Configuration can be set via:
    1. Config file (~/.config/audio-notify-server/config.json or /etc/...)
    2. Environment variables (ELEVENLABS_API_KEY, etc.)

    Environment variables take precedence over config file.

    Returns:
        ElevenLabsConfig with settings for ElevenLabs TTS.

    """
    config = load_config()
    elevenlabs_config = config.get("elevenlabs", {})

    # API key: env var takes precedence
    api_key = os.environ.get("ELEVENLABS_API_KEY") or elevenlabs_config.get("api_key")

    # Enabled: true if API key is set and not explicitly disabled
    enabled = elevenlabs_config.get("enabled", True) and api_key is not None

    # Voice and model settings
    voice_id = (
        os.environ.get("ELEVENLABS_VOICE_ID")
        or elevenlabs_config.get("voice_id")
        or DEFAULT_ELEVENLABS_VOICE_ID
    )
    model_id = (
        os.environ.get("ELEVENLABS_MODEL_ID")
        or elevenlabs_config.get("model_id")
        or DEFAULT_ELEVENLABS_MODEL_ID
    )

    return ElevenLabsConfig(
        enabled=enabled,
        api_key=api_key,
        voice_id=voice_id,
        model_id=model_id,
    )
