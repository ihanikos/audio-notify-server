"""Centralized logging configuration using Loguru.

Provides structured logging with rotation, writing to XDG-compliant directories
rather than the repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

# Default log directory follows XDG spec: ~/.local/state/<app>/
# Falls back to ~/.local/state/audio-notify-server/
DEFAULT_LOG_DIR = Path.home() / ".local" / "state" / "audio-notify-server"

# Remove default handler
logger.remove()


def setup_logging(  # noqa: PLR0913
    log_dir: Path | str | None = None,
    level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "7 days",
    *,
    json_logs: bool = False,
    console: bool = True,
) -> None:
    """
    Configure logging with rotation and optional JSON output.

    Args:
        log_dir: Directory for log files. Defaults to ~/.local/state/audio-notify-server/
                 Set to None to disable file logging.
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        rotation: When to rotate logs (e.g., "10 MB", "1 day", "00:00")
        retention: How long to keep old logs (e.g., "7 days", "1 month", 10)
        json_logs: If True, write JSON-formatted logs to file
        console: If True, also log to stderr with colors
    """
    # Console handler (stderr with colors)
    if console:
        logger.add(
            sys.stderr,
            level=level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>",
            colorize=True,
        )

    # File handler with rotation
    if log_dir is not None:
        log_path = Path(log_dir) if isinstance(log_dir, str) else log_dir
        log_path.mkdir(parents=True, exist_ok=True)

        log_file = log_path / "audio-notify-server.log"

        if json_logs:
            # JSON format for structured logging / log aggregation
            logger.add(
                log_file,
                level=level,
                rotation=rotation,
                retention=retention,
                compression="gz",
                serialize=True,  # JSON output
            )
        else:
            # Plain text format
            logger.add(
                log_file,
                level=level,
                rotation=rotation,
                retention=retention,
                compression="gz",
                format=(
                    "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
                    "{name}:{function}:{line} | {message}"
                ),
            )


def get_logger(name: str = "audio_notify_server"):
    """Get a logger instance bound with the given name."""
    return logger.bind(name=name)
