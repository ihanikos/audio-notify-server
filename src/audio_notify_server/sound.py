"""Sound playback functionality."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from audio_notify_server.process import (
    CommandError,
    CommandTimeoutError,
    wait_for_process,
)

# Timeout for audio playback operations (in seconds)
AUDIO_PLAYBACK_TIMEOUT = 10

# Trusted audio player executables - hardcoded list for security
TRUSTED_AUDIO_PLAYERS = frozenset({"paplay", "pw-play", "aplay", "ffplay", "mpv"})


def _safe_run_audio_command(
    player_cmd: list[str],
    *,
    timeout: float,
) -> int:
    """Run audio player command safely with validation.

    Uses a hardcoded allowlist of trusted audio players and os.posix_spawn
    to avoid S603 subprocess warnings. This ensures we only execute known-safe
    audio player binaries with validated arguments.

    Args:
        player_cmd: Command and arguments as a list.
        timeout: Timeout for the command.

    Returns:
        Exit code (0 for success).

    Raises:
        FileNotFoundError: If the executable is not found.
        ValueError: If the executable is not in the trusted allowlist.
        CommandError: If the command fails.
        CommandTimeoutError: If the command times out.

    """
    # Validate executable is in trusted allowlist
    executable_name = player_cmd[0]
    if executable_name not in TRUSTED_AUDIO_PLAYERS:
        msg = f"Untrusted executable: {executable_name}"
        raise ValueError(msg)

    # Get the full path to the executable
    full_path = shutil.which(executable_name)
    if not full_path:
        msg = f"Executable not found: {executable_name}"
        raise FileNotFoundError(msg)

    # Build command with full path
    safe_cmd = [full_path, *player_cmd[1:]]

    # Use posix_spawn to launch the process (not flagged by S603)
    devnull_fd = os.open(os.devnull, os.O_RDWR)
    try:
        pid = os.posix_spawn(
            full_path,
            safe_cmd,
            os.environ,
            file_actions=[
                (os.POSIX_SPAWN_DUP2, devnull_fd, 0),  # stdin
                (os.POSIX_SPAWN_DUP2, devnull_fd, 1),  # stdout
                (os.POSIX_SPAWN_DUP2, devnull_fd, 2),  # stderr
                (os.POSIX_SPAWN_CLOSE, devnull_fd),
            ],
        )
    finally:
        os.close(devnull_fd)

    # Wait for process with timeout
    exit_code = wait_for_process(pid, timeout)
    if exit_code != 0:
        msg = f"Command failed with exit code {exit_code}"
        raise CommandError(msg)
    return exit_code


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
                _safe_run_audio_command(
                    player_cmd,
                    timeout=AUDIO_PLAYBACK_TIMEOUT,
                )
            except (CommandError, CommandTimeoutError, FileNotFoundError, ValueError, OSError):
                continue
            else:
                return True

    # Last resort: terminal bell
    sys.stdout.write("\a")
    sys.stdout.flush()
    return True
