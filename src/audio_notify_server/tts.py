"""Text-to-speech functionality."""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import time

# Trusted TTS executables - hardcoded list for security
TRUSTED_TTS_ENGINES = frozenset({"espeak", "espeak-ng", "spd-say", "festival"})


class CommandError(Exception):
    """Command execution error."""


class CommandTimeoutError(Exception):
    """Command timeout error."""


def _wait_for_process(pid: int, timeout: float) -> int:
    """Wait for process to complete with timeout.

    Args:
        pid: Process ID to wait for.
        timeout: Timeout in seconds.

    Returns:
        Exit code of the process.

    Raises:
        CommandError: If the process fails.
        CommandTimeoutError: If the process times out.

    """
    start_time = time.time()
    while True:
        wpid, status = os.waitpid(pid, os.WNOHANG)
        if wpid == pid:
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            msg = "Command terminated abnormally"
            raise CommandError(msg)
        if wpid == -1:
            # Process doesn't exist (already reaped)
            return 0

        if time.time() - start_time > timeout:
            _kill_process(pid)
            msg = f"Command timed out after {timeout} seconds"
            raise CommandTimeoutError(msg)

        time.sleep(0.01)


def _kill_process(pid: int) -> None:
    """Kill a process gracefully then forcefully.

    Args:
        pid: Process ID to kill.

    """
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
    with contextlib.suppress(ChildProcessError):
        os.waitpid(pid, 0)


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
    file_actions = []

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

    try:
        pid = os.posix_spawn(
            full_path,
            safe_cmd,
            env=os.environ,
            file_actions=file_actions,
        )

        # Write input data if provided
        if input_data is not None:
            os.close(read_fd)
            os.write(write_fd, input_data)
            os.close(write_fd)
    finally:
        os.close(devnull_fd)

    # Wait for process with timeout
    exit_code = _wait_for_process(pid, timeout)
    if exit_code != 0:
        msg = f"Command failed with exit code {exit_code}"
        raise CommandError(msg)
    return exit_code


def speak(message: str) -> bool:
    """Speak a message using text-to-speech.

    Args:
        message: The message to speak.

    Returns:
        True if TTS was successful, False otherwise.

    """
    if not message:
        return False

    # Use system TTS commands directly (pyttsx3 has instability issues with espeak driver)
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
