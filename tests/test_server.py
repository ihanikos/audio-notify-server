"""Tests for audio-notify-server."""

from collections.abc import Generator
from http import HTTPStatus
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from audio_notify_server.server import create_app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create test client."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client: TestClient) -> None:
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


@patch("audio_notify_server.server.play_sound", return_value=True)
def test_notify_post_default(mock_play_sound: MagicMock, client: TestClient) -> None:
    """Test POST /notify with defaults."""
    response = client.post("/notify", json={})
    assert response.status_code == HTTPStatus.OK
    data: dict[str, Any] = response.json()
    assert data["success"] is True
    assert len(data["actions"]) == 1
    assert data["actions"][0]["type"] == "sound"
    assert data["actions"][0]["success"] is True
    mock_play_sound.assert_called_once()


@patch("audio_notify_server.server.speak", return_value=True)
@patch("audio_notify_server.server.play_sound", return_value=True)
def test_notify_post_with_message(
    mock_play_sound: MagicMock,
    mock_speak: MagicMock,
    client: TestClient,
) -> None:
    """Test POST /notify with message and speak."""
    response = client.post(
        "/notify",
        json={"message": "Test message", "speak": True, "sound": False},
    )
    assert response.status_code == HTTPStatus.OK
    data: dict[str, Any] = response.json()
    assert data["success"] is True
    assert len(data["actions"]) == 1
    assert data["actions"][0]["type"] == "tts"
    assert data["actions"][0]["success"] is True
    mock_play_sound.assert_not_called()
    mock_speak.assert_called_once_with("Test message")


@patch("audio_notify_server.server.play_sound", return_value=True)
def test_notify_get(mock_play_sound: MagicMock, client: TestClient) -> None:
    """Test GET /notify."""
    response = client.get("/notify?sound=true")
    assert response.status_code == HTTPStatus.OK
    data: dict[str, Any] = response.json()
    assert data["success"] is True
    mock_play_sound.assert_called_once()


@patch("audio_notify_server.server.speak", return_value=True)
@patch("audio_notify_server.server.play_sound", return_value=True)
def test_notify_get_with_message(
    mock_play_sound: MagicMock,
    mock_speak: MagicMock,
    client: TestClient,
) -> None:
    """Test GET /notify with message."""
    response = client.get("/notify?message=Hello&speak=true&sound=false")
    assert response.status_code == HTTPStatus.OK
    data: dict[str, Any] = response.json()
    assert data["success"] is True
    mock_play_sound.assert_not_called()
    mock_speak.assert_called_once_with("Hello")


@patch("audio_notify_server.server.speak", return_value=True)
@patch("audio_notify_server.server.play_sound", return_value=True)
def test_notify_sound_and_speak(
    mock_play_sound: MagicMock,
    mock_speak: MagicMock,
    client: TestClient,
) -> None:
    """Test POST /notify with both sound and speak enabled."""
    response = client.post(
        "/notify",
        json={"message": "Build complete", "speak": True, "sound": True},
    )
    assert response.status_code == HTTPStatus.OK
    data: dict[str, Any] = response.json()
    assert data["success"] is True
    expected_actions_count = 2  # Sound and TTS
    assert len(data["actions"]) == expected_actions_count
    mock_play_sound.assert_called_once()
    mock_speak.assert_called_once_with("Build complete")


@patch("audio_notify_server.server.play_sound", return_value=False)
def test_notify_sound_failure(mock_play_sound: MagicMock, client: TestClient) -> None:
    """Test POST /notify when sound playback fails."""
    response = client.post("/notify", json={})
    assert response.status_code == HTTPStatus.OK
    data: dict[str, Any] = response.json()
    assert data["success"] is True
    assert data["actions"][0]["success"] is False
    mock_play_sound.assert_called_once()


def test_openapi_schema(client: TestClient) -> None:
    """Test that OpenAPI schema is available."""
    response = client.get("/openapi.json")
    assert response.status_code == HTTPStatus.OK
    schema: dict[str, Any] = response.json()
    assert schema["info"]["title"] == "Audio Notify Server"
    assert "/notify" in schema["paths"]
    assert "/health" in schema["paths"]


def test_notify_post_message_too_long(client: TestClient) -> None:
    """Test POST /notify rejects messages exceeding max length."""
    with patch("audio_notify_server.server.get_max_message_length", return_value=50):
        long_message = "x" * 51
        response = client.post("/notify", json={"message": long_message, "speak": True})
        assert response.status_code == HTTPStatus.BAD_REQUEST
        data: dict[str, Any] = response.json()
        assert "Message too long" in data["detail"]
        assert "51 characters" in data["detail"]
        assert "50 characters" in data["detail"]
        assert "Please summarize" in data["detail"]


def test_notify_get_message_too_long(client: TestClient) -> None:
    """Test GET /notify rejects messages exceeding max length."""
    with patch("audio_notify_server.server.get_max_message_length", return_value=50):
        long_message = "x" * 51
        response = client.get(f"/notify?message={long_message}&speak=true")
        assert response.status_code == HTTPStatus.BAD_REQUEST
        data: dict[str, Any] = response.json()
        assert "Message too long" in data["detail"]
        assert "Please summarize" in data["detail"]


def test_notify_post_logs_message(client: TestClient) -> None:
    """Test POST /notify logs the message content."""
    with (
        patch("audio_notify_server.server.play_sound", return_value=True),
        patch("audio_notify_server.server.logger") as mock_logger,
    ):
        response = client.post(
            "/notify",
            json={"message": "Test log message", "speak": False, "sound": True},
        )
        assert response.status_code == HTTPStatus.OK

        # Check that logger.info was called with message content
        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("Test log message" in call for call in log_calls)


def test_notify_get_logs_message(client: TestClient) -> None:
    """Test GET /notify logs the message content."""
    with (
        patch("audio_notify_server.server.play_sound", return_value=True),
        patch("audio_notify_server.server.logger") as mock_logger,
    ):
        response = client.get("/notify?message=Hello%20from%20GET&sound=true")
        assert response.status_code == HTTPStatus.OK

        # Check that logger.info was called with message content
        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("Hello from GET" in call for call in log_calls)


def test_notify_logs_client_ip(client: TestClient) -> None:
    """Test /notify logs the client IP address."""
    with (
        patch("audio_notify_server.server.play_sound", return_value=True),
        patch("audio_notify_server.server.logger") as mock_logger,
    ):
        response = client.post("/notify", json={})
        assert response.status_code == HTTPStatus.OK

        # Check that logger.info was called with client IP info
        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        # TestClient uses 'testclient' as the host
        assert any("testclient" in call for call in log_calls)
