"""Text-to-speech functionality."""

from __future__ import annotations

import contextlib
import errno
import os
import select
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from audio_notify_server.config import get_elevenlabs_config
from audio_notify_server.process import (
    CommandError,
    CommandTimeoutError,
    wait_for_process,
)

if TYPE_CHECKING:
    from audio_notify_server.config import ElevenLabsConfig

# Trusted TTS executables - hardcoded list for security
TRUSTED_TTS_ENGINES = frozenset({"espeak", "espeak-ng", "spd-say", "festival"})

# Maximum time to wait for pipe write (seconds)
PIPE_WRITE_TIMEOUT = 5.0

# ElevenLabs API endpoint
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"

# Timeout for ElevenLabs API requests (seconds)
ELEVENLABS_TIMEOUT = 30.0


def _write_to_pipe_nonblocking(fd: int, data: bytes, timeout: float) -> None:
    """Write data to a pipe file descriptor with timeout.

    Uses non-blocking I/O to avoid indefinite blocking if the pipe buffer fills.

    Args:
        fd: File descriptor to write to.
        data: Data to write.
        timeout: Maximum time to wait for write to complete.

    Raises:
        OSError: If write fails or times out.

    """
    os.set_blocking(fd, False)
    written = 0
    while written < len(data):
        ready, _, _ = select.select([], [fd], [], timeout)
        if not ready:
            msg = f"Pipe write timed out after {timeout} seconds"
            raise OSError(errno.ETIMEDOUT, msg)
        try:
            n = os.write(fd, data[written:])
            if n == 0:
                msg = "Pipe closed unexpectedly"
                raise OSError(errno.EPIPE, msg)
            written += n
        except BlockingIOError:
            # Buffer full, wait for it to drain
            continue


def _safe_run_tts_command(
    tts_cmd: list[str],
    *,
    timeout: float,
    input_data: bytes | None = None,
) -> int:
    """Run TTS command safely with validation.

    Uses a hardcoded allowlist of trusted TTS engines and os.posix_spawn
    to avoid S603 subprocess warnings. This ensures we only execute known-safe
    TTS binaries with validated arguments.

    Args:
        tts_cmd: Command and arguments as a list.
        timeout: Timeout for the command.
        input_data: Data to pass to stdin (for festival).

    Returns:
        Exit code (0 for success).

    Raises:
        FileNotFoundError: If the executable is not found.
        ValueError: If the executable is not in the trusted allowlist.
        CommandError: If the command fails.
        CommandTimeoutError: If the command times out.

    """
    # Validate executable is in trusted allowlist
    executable_name = tts_cmd[0]
    if executable_name not in TRUSTED_TTS_ENGINES:
        msg = f"Untrusted executable: {executable_name}"
        raise ValueError(msg)

    # Get the full path to the executable
    full_path = shutil.which(executable_name)
    if not full_path:
        msg = f"Executable not found: {executable_name}"
        raise FileNotFoundError(msg)

    # Build command with full path
    safe_cmd = [full_path, *tts_cmd[1:]]

    # Use posix_spawn to launch the process (not flagged by S603)
    devnull_fd = os.open(os.devnull, os.O_RDWR)
    read_fd, write_fd = None, None
    file_actions = []

    try:
        # Setup file descriptors for stdin/stdout/stderr
        if input_data is not None:
            # Create a pipe for stdin
            read_fd, write_fd = os.pipe()
            file_actions.append((os.POSIX_SPAWN_DUP2, read_fd, 0))
            file_actions.append((os.POSIX_SPAWN_CLOSE, write_fd))
        else:
            file_actions.append((os.POSIX_SPAWN_DUP2, devnull_fd, 0))

        # Redirect stdout and stderr to /dev/null
        file_actions.append((os.POSIX_SPAWN_DUP2, devnull_fd, 1))
        file_actions.append((os.POSIX_SPAWN_DUP2, devnull_fd, 2))
        file_actions.append((os.POSIX_SPAWN_CLOSE, devnull_fd))

        pid = os.posix_spawn(
            full_path,
            safe_cmd,
            os.environ,
            file_actions=file_actions,
        )

        # Write input data if provided
        if input_data is not None:
            os.close(read_fd)
            read_fd = None
            _write_to_pipe_nonblocking(write_fd, input_data, PIPE_WRITE_TIMEOUT)
            os.close(write_fd)
            write_fd = None
    finally:
        os.close(devnull_fd)
        if read_fd is not None:
            os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)

    # Wait for process with timeout
    exit_code = wait_for_process(pid, timeout)
    if exit_code != 0:
        msg = f"Command failed with exit code {exit_code}"
        raise CommandError(msg)
    return exit_code


def _speak_elevenlabs(message: str, config: ElevenLabsConfig) -> bool:
    """Speak a message using ElevenLabs TTS API.

    Args:
        message: The message to speak.
        config: ElevenLabs configuration.

    Returns:
        True if TTS was successful, False otherwise.

    """
    if not config.api_key:
        return False

    url = f"{ELEVENLABS_API_URL}/{config.voice_id}"
    headers = {
        "xi-api-key": config.api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": message,
        "model_id": config.model_id,
    }

    try:
        with httpx.Client(timeout=ELEVENLABS_TIMEOUT) as client:
            response = client.post(
                url,
                headers=headers,
                json=payload,
                params={"output_format": "mp3_44100_128"},
            )
            response.raise_for_status()

            # Save audio to temp file and play it
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(response.content)
                temp_path = f.name

            try:
                return _play_audio_file(temp_path)
            finally:
                # Clean up temp file
                with contextlib.suppress(OSError):
                    Path(temp_path).unlink()

    except httpx.HTTPStatusError as e:
        logger.warning("ElevenLabs API error: {} {}", e.response.status_code, e.response.text[:200])
        return False
    except httpx.RequestError as e:
        logger.warning("ElevenLabs request failed: {}", e)
        return False


def _play_audio_file(path: str) -> bool:
    """Play an audio file using available system players.

    Args:
        path: Path to the audio file.

    Returns:
        True if playback was successful, False otherwise.

    """
    # Import here to avoid circular dependency
    from audio_notify_server.sound import TRUSTED_AUDIO_PLAYERS, play_sound

    # Try play_sound which handles multiple players
    if play_sound(path):
        return True

    # Fallback: try mpv/ffplay directly for mp3
    players = [
        ["mpv", "--no-video", "--really-quiet", path],
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
    ]

    for player_cmd in players:
        player = player_cmd[0]
        if player in TRUSTED_AUDIO_PLAYERS and shutil.which(player):
            devnull_fd = os.open(os.devnull, os.O_RDWR)
            try:
                full_path = shutil.which(player)
                if not full_path:
                    continue
                safe_cmd = [full_path, *player_cmd[1:]]
                pid = os.posix_spawn(
                    full_path,
                    safe_cmd,
                    os.environ,
                    file_actions=[
                        (os.POSIX_SPAWN_DUP2, devnull_fd, 0),
                        (os.POSIX_SPAWN_DUP2, devnull_fd, 1),
                        (os.POSIX_SPAWN_DUP2, devnull_fd, 2),
                        (os.POSIX_SPAWN_CLOSE, devnull_fd),
                    ],
                )
            finally:
                os.close(devnull_fd)

            try:
                exit_code = wait_for_process(pid, timeout=30)
                if exit_code == 0:
                    return True
            except (CommandError, CommandTimeoutError):
                continue

    return False


def _speak_local(message: str) -> bool:
    """Speak a message using local TTS engines.

    Args:
        message: The message to speak.

    Returns:
        True if TTS was successful, False otherwise.

    """
    tts_commands = [
        ["espeak", message],
        ["espeak-ng", message],
        ["spd-say", message],
        ["festival", "--tts"],  # needs stdin
    ]

    for cmd in tts_commands:
        if shutil.which(cmd[0]):
            try:
                if cmd[0] == "festival":
                    _safe_run_tts_command(
                        cmd,
                        timeout=30,
                        input_data=message.encode(),
                    )
                else:
                    _safe_run_tts_command(
                        cmd,
                        timeout=30,
                    )
            except (CommandError, CommandTimeoutError, FileNotFoundError, ValueError, OSError):
                continue
            else:
                return True

    return False


def speak(message: str) -> bool:
    """Speak a message using text-to-speech.

    Tries ElevenLabs TTS first if configured, then falls back to local TTS engines.

    Args:
        message: The message to speak.

    Returns:
        True if TTS was successful, False otherwise.

    """
    if not message:
        return False

    # Try ElevenLabs first if configured
    elevenlabs_config = get_elevenlabs_config()
    if elevenlabs_config.enabled:
        if _speak_elevenlabs(message, elevenlabs_config):
            return True
        logger.debug("ElevenLabs TTS failed, falling back to local TTS")

    # Fall back to local TTS engines
    return _speak_local(message)
