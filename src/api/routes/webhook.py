"""Strava webhook endpoint.

Strava sends two types of requests to this endpoint:

1. **Subscription verification** (``GET /webhook/strava``)
   Strava challenges the endpoint when you register a webhook subscription.
   Respond with the ``hub.challenge`` value to confirm ownership.

2. **Event delivery** (``POST /webhook/strava``)
   Strava pushes an event whenever an activity is created, updated, or
   deleted. This endpoint ACKs immediately (HTTP 200) and processes the
   event in a FastAPI ``BackgroundTask`` to stay within Strava's 2-second
   response window.

Registering a webhook subscription
------------------------------------
Run this ``curl`` from a terminal (requires a publicly reachable URL)::

    curl -X POST https://www.strava.com/api/v3/push_subscriptions \\
      -F client_id=YOUR_CLIENT_ID \\
      -F client_secret=YOUR_CLIENT_SECRET \\
      -F callback_url=https://your-domain.com/webhook/strava \\
      -F verify_token=YOUR_WEBHOOK_VERIFY_TOKEN

``YOUR_WEBHOOK_VERIFY_TOKEN`` must match the ``STRAVA_WEBHOOK_VERIFY_TOKEN``
value in your ``.env``.
"""

import hmac
import logging
import os
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from src.database.models import Activity
from src.database.session import get_session
from src.strava.client import StravaClient
from src.sync.pipeline import sync_activity

logger = logging.getLogger(__name__)
router = APIRouter()

# Retry configuration for background syncs
_MAX_SYNC_ATTEMPTS = 3
_RETRY_BASE_DELAY = 2  # seconds; delays: 2s then 4s


class StravaWebhookEvent(BaseModel):
    """Validated shape of a Strava webhook event payload.

    Using a Pydantic model instead of a raw ``dict`` ensures FastAPI returns
    422 on malformed payloads rather than crashing inside the handler.
    """

    object_type: str
    object_id: int
    aspect_type: str
    owner_id: int
    subscription_id: int | None = None
    event_time: int | None = None


# ---------------------------------------------------------------------------
# Subscription verification — GET /webhook/strava
# ---------------------------------------------------------------------------

@router.get("", include_in_schema=False)
async def verify_webhook_subscription(
    hub_mode: str = Query(default=None, alias="hub.mode"),
    hub_challenge: str = Query(default=None, alias="hub.challenge"),
    hub_verify_token: str = Query(default=None, alias="hub.verify_token"),
):
    """Respond to Strava's webhook subscription challenge."""
    expected = os.getenv("STRAVA_WEBHOOK_VERIFY_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="STRAVA_WEBHOOK_VERIFY_TOKEN is not configured on this server.",
        )
    # Constant-time comparison prevents timing-based token extraction
    if not hmac.compare_digest(hub_verify_token or "", expected):
        raise HTTPException(status_code=403, detail="Invalid verify token.")
    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail=f"Unexpected hub.mode: {hub_mode!r}")
    if not hub_challenge:
        raise HTTPException(status_code=400, detail="Missing hub.challenge.")

    return {"hub.challenge": hub_challenge}


# ---------------------------------------------------------------------------
# Event delivery — POST /webhook/strava
# ---------------------------------------------------------------------------

@router.post("", status_code=200)
async def receive_webhook_event(
    event: StravaWebhookEvent,
    background_tasks: BackgroundTasks,
):
    """Receive a Strava activity event and process it asynchronously.

    Strava expects a 200 response within 2 seconds. All DB writes and load
    calculations run in a background task after the response is sent.

    Event payload shape::

        {
            "object_type": "activity",
            "object_id": 12345678,
            "aspect_type": "create" | "update" | "delete",
            "owner_id": 98765,
            "subscription_id": 1,
            "event_time": 1609459200
        }
    """
    logger.info(
        "Webhook event: object_type=%s aspect_type=%s object_id=%s owner_id=%s",
        event.object_type, event.aspect_type, event.object_id, event.owner_id,
    )

    # Validate owner_id against the configured athlete to reject events from
    # unknown athletes (including spoofed requests from third parties).
    allowed_athlete_id = os.getenv("STRAVA_ATHLETE_ID")
    if allowed_athlete_id and str(event.owner_id) != allowed_athlete_id:
        logger.warning(
            "Webhook event from unknown owner_id %s — rejecting", event.owner_id
        )
        return {"status": "ignored"}

    if event.object_type != "activity":
        return {"status": "ignored"}

    if event.aspect_type in ("create", "update"):
        background_tasks.add_task(_background_sync, event.object_id)
    elif event.aspect_type == "delete":
        background_tasks.add_task(_background_delete, event.object_id)

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Background task helpers (run after the HTTP response is sent)
# ---------------------------------------------------------------------------

def _background_sync(activity_id: int) -> None:
    """Fetch and sync one activity from Strava with exponential-backoff retries."""
    for attempt in range(1, _MAX_SYNC_ATTEMPTS + 1):
        try:
            client = StravaClient()
            with get_session() as session:
                result = sync_activity(client, activity_id, session)
            logger.info("Background sync complete: %s", result)
            return
        except Exception:
            if attempt == _MAX_SYNC_ATTEMPTS:
                logger.exception(
                    "Background sync permanently failed for activity %s after %d attempts",
                    activity_id, _MAX_SYNC_ATTEMPTS,
                )
            else:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))  # 2s, 4s
                logger.warning(
                    "Background sync attempt %d/%d failed for activity %s, retrying in %ds",
                    attempt, _MAX_SYNC_ATTEMPTS, activity_id, delay,
                )
                time.sleep(delay)


def _background_delete(activity_id: int) -> None:
    """Delete a local activity when Strava signals it was removed."""
    try:
        with get_session() as session:
            activity = (
                session.query(Activity)
                .filter(Activity.strava_activity_id == activity_id)
                .first()
            )
            if activity:
                session.delete(activity)
                logger.info("Deleted activity %s from database", activity_id)
            else:
                logger.debug(
                    "Delete event for unknown activity %s — nothing to remove",
                    activity_id,
                )
    except Exception:
        logger.exception("Background delete failed for activity %s", activity_id)
