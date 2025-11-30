"""Notification server implementation using FastAPI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel, Field

from .config import get_max_message_length
from .logging import DEFAULT_LOG_DIR, LogConfig, setup_logging
from .sound import play_sound
from .tts import speak

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class NotifyRequest(BaseModel):
    """Request body for POST /notify."""

    message: str = Field(default="", description="Message to speak via TTS")
    sound: bool = Field(default=True, description="Whether to play notification sound")
    speak: bool = Field(default=False, description="Whether to speak the message via TTS")


class ActionResult(BaseModel):
    """Result of a single notification action."""

    type: str = Field(description="Type of action: 'sound' or 'tts'")
    success: bool = Field(description="Whether the action succeeded")
    message: str | None = Field(default=None, description="The message that was spoken (for TTS)")


class NotifyResponse(BaseModel):
    """Response from /notify endpoint."""

    success: bool = Field(description="Overall success status")
    actions: list[ActionResult] = Field(description="List of actions performed")


class HealthResponse(BaseModel):
    """Response from /health endpoint."""

    status: str = Field(description="Health status")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    logger.info("Audio notify server starting up")
    yield
    logger.info("Audio notify server shutting down")


def create_app(sound_file: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        sound_file: Optional path to custom notification sound.

    Returns:
        Configured FastAPI application.

    """
    app = FastAPI(
        title="Audio Notify Server",
        description="A lightweight local notification server for remote task completion alerts. "
        "Plays sounds and optionally speaks messages via TTS.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store config in app.state instead of global variable
    app.state.sound_file = sound_file

    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check",
        description="Check if the server is running.",
    )
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post(
        "/notify",
        response_model=NotifyResponse,
        summary="Send notification",
        description="Trigger a notification with optional sound and TTS.",
    )
    async def notify_post(body: NotifyRequest, request: Request) -> NotifyResponse:
        max_length = get_max_message_length()
        if len(body.message) > max_length:
            raise HTTPException(
                status_code=400,
                detail=f"Message too long ({len(body.message)} characters). "
                f"Maximum allowed length is {max_length} characters. "
                "Please summarize your message.",
            )

        client_ip = request.client.host if request.client else "unknown"
        actions: list[ActionResult] = []

        # Log the notification request
        logger.info(
            "Notification received from {} | message={!r} sound={} speak={}",
            client_ip,
            body.message or "(none)",
            body.sound,
            body.speak,
        )

        if body.sound:
            sound_played = play_sound(request.app.state.sound_file)
            actions.append(ActionResult(type="sound", success=sound_played))
            logger.debug("Sound playback", success=sound_played)

        if body.speak and body.message:
            spoken = speak(body.message)
            actions.append(ActionResult(type="tts", success=spoken, message=body.message))
            logger.debug("TTS playback", success=spoken, message=body.message)

        # Log notification result
        logger.info(
            "Notification completed from {} | actions={} all_success={}",
            client_ip,
            len(actions),
            all(a.success for a in actions),
        )

        return NotifyResponse(success=True, actions=actions)

    @app.get(
        "/notify",
        response_model=NotifyResponse,
        summary="Send notification (GET)",
        description="Trigger a notification via GET request with query parameters.",
    )
    async def notify_get(
        request: Request,
        message: Annotated[str, Query(description="Message to speak via TTS")] = "",
        *,
        sound: Annotated[bool, Query(description="Whether to play notification sound")] = True,
        speak_msg: Annotated[
            bool, Query(alias="speak", description="Whether to speak the message via TTS"),
        ] = False,
    ) -> NotifyResponse:
        max_length = get_max_message_length()
        if len(message) > max_length:
            raise HTTPException(
                status_code=400,
                detail=f"Message too long ({len(message)} characters). "
                f"Maximum allowed length is {max_length} characters. "
                "Please summarize your message.",
            )

        client_ip = request.client.host if request.client else "unknown"
        actions: list[ActionResult] = []

        # Log the notification request
        logger.info(
            "Notification received (GET) from {} | message={!r} sound={} speak={}",
            client_ip,
            message or "(none)",
            sound,
            speak_msg,
        )

        if sound:
            sound_played = play_sound(request.app.state.sound_file)
            actions.append(ActionResult(type="sound", success=sound_played))
            logger.debug("Sound playback", success=sound_played)

        if speak_msg and message:
            spoken = speak(message)
            actions.append(ActionResult(type="tts", success=spoken, message=message))
            logger.debug("TTS playback", success=spoken, message=message)

        # Log notification result
        logger.info(
            "Notification completed from {} | actions={} all_success={}",
            client_ip,
            len(actions),
            all(a.success for a in actions),
        )

        return NotifyResponse(success=True, actions=actions)

    return app


def run_server(
    host: str = "127.0.0.1",
    port: int = 51515,
    sound_file: str | None = None,
    *,
    debug: bool = False,
) -> None:
    """Run the notification server.

    Args:
        host: Interface to bind to (default: 127.0.0.1 for security)
        port: Port to listen on (default: 51515)
        sound_file: Optional path to custom notification sound
        debug: Enable debug mode

    """
    # Configure logging
    log_config = LogConfig(
        log_dir=DEFAULT_LOG_DIR,
        level="DEBUG" if debug else "INFO",
        json_logs=False,  # Plain text for readability; set True for log aggregation
    )
    setup_logging(log_config)

    logger.info("Starting notification server on {}:{}", host, port)

    app = create_app(sound_file=sound_file)
    uvicorn.run(app, host=host, port=port, log_level="debug" if debug else "info")
