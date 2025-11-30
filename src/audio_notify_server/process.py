"""Process management utilities for safe command execution."""

from __future__ import annotations

import contextlib
import os
import signal
import time


class CommandError(Exception):
    """Command execution error."""


class CommandTimeoutError(Exception):
    """Command timeout error."""


def wait_for_process(pid: int, timeout: float) -> int:
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
        try:
            wpid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            # Process doesn't exist (already reaped)
            return 0
        if wpid == pid:
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            msg = "Command terminated abnormally"
            raise CommandError(msg)

        if time.time() - start_time > timeout:
            kill_process(pid)
            msg = f"Command timed out after {timeout} seconds"
            raise CommandTimeoutError(msg)

        time.sleep(0.01)


def kill_process(pid: int) -> None:
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
