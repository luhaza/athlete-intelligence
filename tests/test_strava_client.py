"""Tests for src/strava/client.py."""

import pytest
from unittest.mock import MagicMock, patch

from src.strava.client import StravaClient, STRAVA_API_BASE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return StravaClient(access_token="test_token_123")


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_client_init_with_explicit_token():
    c = StravaClient(access_token="explicit_token")
    assert c._session.headers["Authorization"] == "Bearer explicit_token"


def test_client_init_from_env(monkeypatch):
    monkeypatch.setenv("STRAVA_ACCESS_TOKEN", "env_token")
    c = StravaClient()
    assert c._session.headers["Authorization"] == "Bearer env_token"


def test_client_init_raises_without_token(monkeypatch):
    monkeypatch.delenv("STRAVA_ACCESS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="access token"):
        StravaClient()


# ---------------------------------------------------------------------------
# get_athlete
# ---------------------------------------------------------------------------

def test_get_athlete(client):
    athlete_data = {"id": 42, "firstname": "Jane", "lastname": "Doe"}
    mock_resp = MagicMock()
    mock_resp.json.return_value = athlete_data
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        result = client.get_athlete()

    mock_get.assert_called_once_with(f"{STRAVA_API_BASE}/athlete", params={})
    assert result == athlete_data


# ---------------------------------------------------------------------------
# get_activities
# ---------------------------------------------------------------------------

def test_get_activities_default_pagination(client):
    activities = [{"id": 1}, {"id": 2}]
    mock_resp = MagicMock()
    mock_resp.json.return_value = activities
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        result = client.get_activities()

    mock_get.assert_called_once_with(
        f"{STRAVA_API_BASE}/athlete/activities",
        params={"page": 1, "per_page": 30},
    )
    assert result == activities


def test_get_activities_custom_pagination(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        client.get_activities(page=3, per_page=50)

    mock_get.assert_called_once_with(
        f"{STRAVA_API_BASE}/athlete/activities",
        params={"page": 3, "per_page": 50},
    )


# ---------------------------------------------------------------------------
# get_activity
# ---------------------------------------------------------------------------

def test_get_activity(client):
    activity = {"id": 99, "name": "Morning Run"}
    mock_resp = MagicMock()
    mock_resp.json.return_value = activity
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        result = client.get_activity(99)

    mock_get.assert_called_once_with(f"{STRAVA_API_BASE}/activities/99", params={})
    assert result == activity


# ---------------------------------------------------------------------------
# get_activity_streams
# ---------------------------------------------------------------------------

def test_get_activity_streams_default_keys(client):
    streams = {"heartrate": {"data": [120, 130]}}
    mock_resp = MagicMock()
    mock_resp.json.return_value = streams
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        result = client.get_activity_streams(99)

    call_kwargs = mock_get.call_args
    assert "time" in call_kwargs.kwargs["params"]["keys"]
    assert "heartrate" in call_kwargs.kwargs["params"]["keys"]
    assert result == streams


def test_get_activity_streams_custom_keys(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        client.get_activity_streams(99, stream_types=["heartrate", "time"])

    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs["params"]["keys"] == "heartrate,time"


# ---------------------------------------------------------------------------
# HTTP error propagation
# ---------------------------------------------------------------------------

def test_http_error_is_raised(client):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")

    with patch.object(client._session, "get", return_value=mock_resp):
        with pytest.raises(Exception, match="401"):
            client.get_athlete()
