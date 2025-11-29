"""Tests for audio-notify-server."""

from http import HTTPStatus
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from audio_notify_server.server import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    with TestClient(app) as client:
        yield client


def test_health_check(client):
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


@patch("audio_notify_server.server.play_sound", return_value=True)
def test_notify_post_default(mock_play_sound, client):
    """Test POST /notify with defaults."""
    response = client.post("/notify", json={})
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
    assert len(data["actions"]) == 1
    assert data["actions"][0]["type"] == "sound"
    assert data["actions"][0]["success"] is True
    mock_play_sound.assert_called_once()


@patch("audio_notify_server.server.speak", return_value=True)
@patch("audio_notify_server.server.play_sound", return_value=True)
def test_notify_post_with_message(mock_play_sound, mock_speak, client):
    """Test POST /notify with message and speak."""
    response = client.post(
        "/notify",
        json={"message": "Test message", "speak": True, "sound": False},
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
    assert len(data["actions"]) == 1
    assert data["actions"][0]["type"] == "tts"
    assert data["actions"][0]["success"] is True
    mock_play_sound.assert_not_called()
    mock_speak.assert_called_once_with("Test message")


@patch("audio_notify_server.server.play_sound", return_value=True)
def test_notify_get(mock_play_sound, client):
    """Test GET /notify."""
    response = client.get("/notify?sound=true")
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
    mock_play_sound.assert_called_once()


@patch("audio_notify_server.server.speak", return_value=True)
@patch("audio_notify_server.server.play_sound", return_value=True)
def test_notify_get_with_message(mock_play_sound, mock_speak, client):
    """Test GET /notify with message."""
    response = client.get("/notify?message=Hello&speak=true&sound=false")
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
    mock_play_sound.assert_not_called()
    mock_speak.assert_called_once_with("Hello")


@patch("audio_notify_server.server.speak", return_value=True)
@patch("audio_notify_server.server.play_sound", return_value=True)
def test_notify_sound_and_speak(mock_play_sound, mock_speak, client):
    """Test POST /notify with both sound and speak enabled."""
    response = client.post(
        "/notify",
        json={"message": "Build complete", "speak": True, "sound": True},
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
    expected_actions_count = 2  # Sound and TTS
    assert len(data["actions"]) == expected_actions_count
    mock_play_sound.assert_called_once()
    mock_speak.assert_called_once_with("Build complete")


@patch("audio_notify_server.server.play_sound", return_value=False)
def test_notify_sound_failure(mock_play_sound, client):
    """Test POST /notify when sound playback fails."""
    response = client.post("/notify", json={})
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["success"] is True
    assert data["actions"][0]["success"] is False
    mock_play_sound.assert_called_once()


def test_openapi_schema(client):
    """Test that OpenAPI schema is available."""
    response = client.get("/openapi.json")
    assert response.status_code == HTTPStatus.OK
    schema = response.json()
    assert schema["info"]["title"] == "Audio Notify Server"
    assert "/notify" in schema["paths"]
    assert "/health" in schema["paths"]
