"""Centralized logging configuration using Loguru.

Provides structured logging with rotation, writing to XDG-compliant directories
rather than the repository root.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# Default log directory follows XDG spec: ~/.local/state/<app>/
# Falls back to ~/.local/state/audio-notify-server/
DEFAULT_LOG_DIR = Path.home() / ".local" / "state" / "audio-notify-server"

# Remove default handler
logger.remove()


@dataclass
class LogConfig:
    """Configuration for logging setup."""

    log_dir: Path | str | None = None
    level: str = "INFO"
    rotation: str = "10 MB"
    retention: str = "7 days"
    json_logs: bool = False
    console: bool = True


def setup_logging(config: LogConfig | None = None) -> None:
    """Configure logging with rotation and optional JSON output.

    Args:
        config: Logging configuration. Uses defaults if None.

    """
    if config is None:
        config = LogConfig()

    # Console handler (stderr with colors)
    if config.console:
        logger.add(
            sys.stderr,
            level=config.level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>",
            colorize=True,
        )

    # File handler with rotation
    if config.log_dir is not None:
        log_dir = config.log_dir
        log_path = Path(log_dir) if isinstance(log_dir, str) else log_dir
        log_path.mkdir(parents=True, exist_ok=True)

        log_file = log_path / "audio-notify-server.log"

        if config.json_logs:
            # JSON format for structured logging / log aggregation
            logger.add(
                log_file,
                level=config.level,
                rotation=config.rotation,
                retention=config.retention,
                compression="gz",
                serialize=True,  # JSON output
            )
        else:
            # Plain text format
            logger.add(
                log_file,
                level=config.level,
                rotation=config.rotation,
                retention=config.retention,
                compression="gz",
                format=(
                    "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
                    "{name}:{function}:{line} | {message}"
                ),
            )


def get_logger(name: str = "audio_notify_server") -> logger:
    """Get a logger instance bound with the given name.

    Args:
        name: The name to bind to the logger instance.

    Returns:
        A loguru logger instance bound with the given name.

    """
    return logger.bind(name=name)
