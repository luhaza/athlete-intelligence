"""Tests for src/strava/client.py."""

import time
import pytest
from unittest.mock import MagicMock, patch, ANY

from src.strava.client import StravaClient, STRAVA_API_BASE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Create a basic client with just an access token."""
    return StravaClient(access_token="test_token_123")


@pytest.fixture
def client_with_refresh():
    """Create a client with refresh token capabilities."""
    return StravaClient(
        access_token="test_token_123",
        refresh_token="test_refresh_token",
        client_id="test_client_id",
        client_secret="test_client_secret",
        expires_at=int(time.time()) + 3600,  # Expires in 1 hour
    )


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_client_init_with_explicit_token():
    c = StravaClient(access_token="explicit_token")
    assert c._access_token == "explicit_token"
    assert c._session.headers["Authorization"] == "Bearer explicit_token"
    assert c._timeout == 10.0


def test_client_init_with_all_params():
    c = StravaClient(
        access_token="access",
        refresh_token="refresh",
        client_id="client_id",
        client_secret="secret",
        expires_at=1234567890,
        timeout=30.0,
    )
    assert c._access_token == "access"
    assert c._refresh_token == "refresh"
    assert c._client_id == "client_id"
    assert c._client_secret == "secret"
    assert c._expires_at == 1234567890
    assert c._timeout == 30.0


def test_client_init_custom_timeout():
    c = StravaClient(access_token="tok", timeout=30.0)
    assert c._timeout == 30.0


def test_client_init_from_env(monkeypatch):
    monkeypatch.setenv("STRAVA_ACCESS_TOKEN", "env_token")
    monkeypatch.setenv("STRAVA_REFRESH_TOKEN", "env_refresh")
    monkeypatch.setenv("STRAVA_CLIENT_ID", "env_client")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "env_secret")
    monkeypatch.setenv("STRAVA_EXPIRES_AT", "1234567890")
    
    c = StravaClient()
    assert c._access_token == "env_token"
    assert c._refresh_token == "env_refresh"
    assert c._client_id == "env_client"
    assert c._client_secret == "env_secret"
    assert c._expires_at == 1234567890
    assert c._session.headers["Authorization"] == "Bearer env_token"


def test_client_init_expires_at_invalid_string(monkeypatch):
    monkeypatch.setenv("STRAVA_ACCESS_TOKEN", "token")
    monkeypatch.setenv("STRAVA_EXPIRES_AT", "invalid")
    
    c = StravaClient()
    assert c._expires_at is None  # Should handle invalid value gracefully


def test_client_init_raises_without_token(monkeypatch):
    monkeypatch.delenv("STRAVA_ACCESS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="access token"):
        StravaClient()


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

def test_refresh_access_token_success(client_with_refresh):
    mock_response_data = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_at": 9999999999,
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response_data
    mock_resp.raise_for_status = MagicMock()
    
    with patch("requests.post", return_value=mock_resp) as mock_post:
        client_with_refresh._refresh_access_token()
    
    # Verify the refresh request
    mock_post.assert_called_once_with(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "grant_type": "refresh_token",
            "refresh_token": "test_refresh_token",
        },
        timeout=10.0,
    )
    
    # Verify tokens were updated
    assert client_with_refresh._access_token == "new_access_token"
    assert client_with_refresh._refresh_token == "new_refresh_token"
    assert client_with_refresh._expires_at == 9999999999
    assert client_with_refresh._session.headers["Authorization"] == "Bearer new_access_token"


def test_refresh_access_token_without_refresh_token(monkeypatch):
    # Ensure no environment variables are set
    monkeypatch.delenv("STRAVA_REFRESH_TOKEN", raising=False)
    
    # Create client after clearing env vars
    client = StravaClient(access_token="test_token")
    
    with pytest.raises(ValueError, match="refresh_token is not set"):
        client._refresh_access_token()


def test_refresh_access_token_without_client_credentials(monkeypatch):
    # Ensure no environment variables are set
    monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
    monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
    
    c = StravaClient(
        access_token="token",
        refresh_token="refresh",
    )
    # Mock requests.post to prevent actual network call
    with patch("requests.post") as mock_post:
        with pytest.raises(ValueError, match="client_id and client_secret are required"):
            c._refresh_access_token()
    # Should not make network call if credentials are missing
    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Token expiration checking
# ---------------------------------------------------------------------------

def test_ensure_valid_token_no_expiry(client):
    """When no expiry is set, should not attempt refresh."""
    with patch.object(client, "_refresh_access_token") as mock_refresh:
        client._ensure_valid_token()
    mock_refresh.assert_not_called()


def test_ensure_valid_token_not_expired(client_with_refresh):
    """When token is valid, should not refresh."""
    with patch.object(client_with_refresh, "_refresh_access_token") as mock_refresh:
        client_with_refresh._ensure_valid_token()
    mock_refresh.assert_not_called()


def test_ensure_valid_token_expired(client_with_refresh):
    """When token is expired, should refresh."""
    # Set token to expire in the past
    client_with_refresh._expires_at = int(time.time()) - 1000
    
    with patch.object(client_with_refresh, "_refresh_access_token") as mock_refresh:
        client_with_refresh._ensure_valid_token()
    mock_refresh.assert_called_once()


def test_ensure_valid_token_expiring_soon(client_with_refresh):
    """When token expires within 5 minutes, should refresh."""
    # Set token to expire in 4 minutes
    client_with_refresh._expires_at = int(time.time()) + 240
    
    with patch.object(client_with_refresh, "_refresh_access_token") as mock_refresh:
        client_with_refresh._ensure_valid_token()
    mock_refresh.assert_called_once()


# ---------------------------------------------------------------------------
# get_athlete
# ---------------------------------------------------------------------------

def test_get_athlete(client):
    athlete_data = {"id": 42, "firstname": "Jane", "lastname": "Doe"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = athlete_data
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        with patch.object(client, "_ensure_valid_token"):
            result = client.get_athlete()

    assert mock_get.call_count >= 1
    assert result == athlete_data


# ---------------------------------------------------------------------------
# get_activities
# ---------------------------------------------------------------------------

def test_get_activities_default_pagination(client):
    activities = [{"id": 1}, {"id": 2}]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = activities
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        with patch.object(client, "_ensure_valid_token"):
            result = client.get_activities()

    assert result == activities


def test_get_activities_custom_pagination(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        with patch.object(client, "_ensure_valid_token"):
            client.get_activities(page=3, per_page=50)

    # Verify the correct params were passed
    call_args = mock_get.call_args
    assert call_args.kwargs["params"]["page"] == 3
    assert call_args.kwargs["params"]["per_page"] == 50


def test_get_activities_per_page_limit():
    """Test that per_page cannot exceed 200."""
    client = StravaClient(access_token="token")
    with pytest.raises(ValueError, match="cannot exceed 200"):
        client.get_activities(per_page=201)


# ---------------------------------------------------------------------------
# get_activity
# ---------------------------------------------------------------------------

def test_get_activity(client):
    activity = {"id": 99, "name": "Morning Run"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = activity
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        with patch.object(client, "_ensure_valid_token"):
            result = client.get_activity(99)

    assert result == activity


# ---------------------------------------------------------------------------
# get_activity_streams
# ---------------------------------------------------------------------------

def test_get_activity_streams_default_keys(client):
    streams = {"heartrate": {"data": [120, 130]}}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = streams
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        with patch.object(client, "_ensure_valid_token"):
            result = client.get_activity_streams(99)

    call_kwargs = mock_get.call_args
    assert "time" in call_kwargs.kwargs["params"]["keys"]
    assert "heartrate" in call_kwargs.kwargs["params"]["keys"]
    assert result == streams


def test_get_activity_streams_custom_keys(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
        with patch.object(client, "_ensure_valid_token"):
            client.get_activity_streams(99, stream_types=["heartrate", "time"])

    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs["params"]["keys"] == "heartrate,time"


# ---------------------------------------------------------------------------
# 401 retry logic
# ---------------------------------------------------------------------------

def test_401_triggers_token_refresh_and_retry(client_with_refresh):
    """Test that a 401 response triggers token refresh and retries."""
    # First response: 401
    mock_resp_401 = MagicMock()
    mock_resp_401.status_code = 401
    
    # Second response: 200 (after refresh)
    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {"id": 42}
    mock_resp_200.raise_for_status = MagicMock()
    
    with patch.object(client_with_refresh._session, "get", side_effect=[mock_resp_401, mock_resp_200]):
        with patch.object(client_with_refresh, "_refresh_access_token") as mock_refresh:
            with patch.object(client_with_refresh, "_ensure_valid_token"):
                result = client_with_refresh.get_athlete()
    
    # Verify refresh was called
    mock_refresh.assert_called_once()
    # Verify we got the result from the retry
    assert result == {"id": 42}


def test_401_without_refresh_token_raises(client):
    """Test that 401 without refresh token raises error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")
    
    with patch.object(client._session, "get", return_value=mock_resp):
        with patch.object(client, "_ensure_valid_token"):
            with pytest.raises(Exception, match="401"):
                client.get_athlete()


# ---------------------------------------------------------------------------
# HTTP error propagation
# ---------------------------------------------------------------------------

def test_http_error_is_raised(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = Exception("500 Server Error")

    with patch.object(client._session, "get", return_value=mock_resp):
        with patch.object(client, "_ensure_valid_token"):
            with pytest.raises(Exception, match="500"):
                client.get_athlete()
