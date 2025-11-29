"""Sound playback functionality."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Timeout for audio playback operations (in seconds)
AUDIO_PLAYBACK_TIMEOUT = 10


def get_default_sound() -> Path | None:
    """Get path to a default system notification sound."""
    # Common locations for notification sounds on Linux
    sound_paths = [
        "/usr/share/sounds/freedesktop/stereo/complete.oga",
        "/usr/share/sounds/freedesktop/stereo/message.oga",
        "/usr/share/sounds/gnome/default/alerts/drip.ogg",
        "/usr/share/sounds/ubuntu/stereo/message.ogg",
        "/usr/share/sounds/sound-icons/prompt.wav",
    ]
    for path in sound_paths:
        if Path(path).exists():
            return Path(path)
    return None


def play_sound(sound_path: str | Path | None = None) -> bool:
    """Play a notification sound.

    Args:
        sound_path: Path to sound file. If None, uses system default.

    Returns:
        True if sound was played successfully, False otherwise.

    """
    if sound_path is None:
        sound_path = get_default_sound()

    if sound_path is None:
        # Fall back to terminal bell
        sys.stdout.write("\a")
        sys.stdout.flush()
        return True

    sound_path = Path(sound_path)
    if not sound_path.exists():
        sys.stdout.write("\a")
        sys.stdout.flush()
        return False

    # Try various audio players
    players = [
        ["paplay", str(sound_path)],  # PulseAudio
        ["pw-play", str(sound_path)],  # PipeWire
        ["aplay", str(sound_path)],  # ALSA
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(sound_path)],
        ["mpv", "--no-video", "--really-quiet", str(sound_path)],
    ]

    for player_cmd in players:
        player = player_cmd[0]
        if shutil.which(player):
            try:
                # S603: subprocess call is safe - using hardcoded command list with validated paths
                # S607: subprocess uses partial executable path - relying on PATH for audio players
                subprocess.run(  # noqa: S603
                    player_cmd,
                    check=True,
                    capture_output=True,
                    timeout=AUDIO_PLAYBACK_TIMEOUT,
                    shell=False,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                continue
            else:
                return True

    # Last resort: terminal bell
    sys.stdout.write("\a")
    sys.stdout.flush()
    return True
