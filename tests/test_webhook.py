"""Tests for src/api/routes/webhook.py"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /webhook/strava — subscription verification
# ---------------------------------------------------------------------------

def test_verify_challenge_valid_token(client, monkeypatch):
    monkeypatch.setenv("STRAVA_WEBHOOK_VERIFY_TOKEN", "mysecret")
    resp = client.get(
        "/webhook/strava",
        params={"hub.mode": "subscribe", "hub.challenge": "abc123", "hub.verify_token": "mysecret"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"hub.challenge": "abc123"}


def test_verify_challenge_invalid_token(client, monkeypatch):
    monkeypatch.setenv("STRAVA_WEBHOOK_VERIFY_TOKEN", "mysecret")
    resp = client.get(
        "/webhook/strava",
        params={"hub.mode": "subscribe", "hub.challenge": "abc123", "hub.verify_token": "wrong"},
    )
    assert resp.status_code == 403


def test_verify_challenge_no_token_configured(client, monkeypatch):
    monkeypatch.delenv("STRAVA_WEBHOOK_VERIFY_TOKEN", raising=False)
    resp = client.get(
        "/webhook/strava",
        params={"hub.mode": "subscribe", "hub.challenge": "abc123", "hub.verify_token": "anything"},
    )
    assert resp.status_code == 500


def test_verify_challenge_wrong_mode(client, monkeypatch):
    monkeypatch.setenv("STRAVA_WEBHOOK_VERIFY_TOKEN", "mysecret")
    resp = client.get(
        "/webhook/strava",
        params={"hub.mode": "unsubscribe", "hub.challenge": "abc123", "hub.verify_token": "mysecret"},
    )
    assert resp.status_code == 400


def test_verify_challenge_missing_challenge(client, monkeypatch):
    monkeypatch.setenv("STRAVA_WEBHOOK_VERIFY_TOKEN", "mysecret")
    resp = client.get(
        "/webhook/strava",
        params={"hub.mode": "subscribe", "hub.verify_token": "mysecret"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /webhook/strava — event delivery
# ---------------------------------------------------------------------------

def test_post_create_event_accepted(client, monkeypatch):
    monkeypatch.delenv("STRAVA_ATHLETE_ID", raising=False)
    with patch("src.api.routes.webhook._background_sync"):
        resp = client.post("/webhook/strava", json={
            "object_type": "activity",
            "object_id": 12345,
            "aspect_type": "create",
            "owner_id": 99,
        })
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_post_update_event_accepted(client, monkeypatch):
    monkeypatch.delenv("STRAVA_ATHLETE_ID", raising=False)
    with patch("src.api.routes.webhook._background_sync"):
        resp = client.post("/webhook/strava", json={
            "object_type": "activity",
            "object_id": 12345,
            "aspect_type": "update",
            "owner_id": 99,
        })
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_post_delete_event_accepted(client, monkeypatch):
    monkeypatch.delenv("STRAVA_ATHLETE_ID", raising=False)
    with patch("src.api.routes.webhook._background_delete"):
        resp = client.post("/webhook/strava", json={
            "object_type": "activity",
            "object_id": 12345,
            "aspect_type": "delete",
            "owner_id": 99,
        })
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_post_event_wrong_owner_rejected(client, monkeypatch):
    monkeypatch.setenv("STRAVA_ATHLETE_ID", "111")
    resp = client.post("/webhook/strava", json={
        "object_type": "activity",
        "object_id": 12345,
        "aspect_type": "create",
        "owner_id": 999,
    })
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}


def test_post_event_correct_owner_accepted(client, monkeypatch):
    monkeypatch.setenv("STRAVA_ATHLETE_ID", "111")
    with patch("src.api.routes.webhook._background_sync"):
        resp = client.post("/webhook/strava", json={
            "object_type": "activity",
            "object_id": 12345,
            "aspect_type": "create",
            "owner_id": 111,
        })
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_post_non_activity_object_ignored(client, monkeypatch):
    monkeypatch.delenv("STRAVA_ATHLETE_ID", raising=False)
    resp = client.post("/webhook/strava", json={
        "object_type": "athlete",
        "object_id": 12345,
        "aspect_type": "update",
        "owner_id": 99,
    })
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}


def test_post_malformed_payload_non_integer_object_id(client, monkeypatch):
    monkeypatch.delenv("STRAVA_ATHLETE_ID", raising=False)
    resp = client.post("/webhook/strava", json={
        "object_type": "activity",
        "object_id": "not_an_int",
        "aspect_type": "create",
        "owner_id": 99,
    })
    assert resp.status_code == 422


def test_post_missing_required_fields(client, monkeypatch):
    monkeypatch.delenv("STRAVA_ATHLETE_ID", raising=False)
    resp = client.post("/webhook/strava", json={"object_type": "activity"})
    assert resp.status_code == 422


def test_post_unknown_aspect_type_returns_ok(client, monkeypatch):
    """Unknown aspect types should be silently ignored, not crash."""
    monkeypatch.delenv("STRAVA_ATHLETE_ID", raising=False)
    resp = client.post("/webhook/strava", json={
        "object_type": "activity",
        "object_id": 12345,
        "aspect_type": "unknown_future_type",
        "owner_id": 99,
    })
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
