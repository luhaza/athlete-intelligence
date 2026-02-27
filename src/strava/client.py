"""Strava API client.

Uses an existing OAuth access token to fetch athlete data and activities
from the Strava v3 API (https://developers.strava.com/docs/reference/).
"""

import os
from typing import Any

import requests


STRAVA_API_BASE = "https://www.strava.com/api/v3"


class StravaClient:
    """Thin wrapper around the Strava v3 REST API.

    Parameters
    ----------
    access_token:
        A valid Strava OAuth access token. When omitted the value is read
        from the ``STRAVA_ACCESS_TOKEN`` environment variable.
    timeout:
        Timeout in seconds for all HTTP requests. Defaults to 10 seconds.
    """

    def __init__(self, access_token: str | None = None, timeout: float = 10.0) -> None:
        token = access_token or os.environ.get("STRAVA_ACCESS_TOKEN")
        if not token:
            raise ValueError(
                "A Strava access token must be provided either as an argument "
                "or via the STRAVA_ACCESS_TOKEN environment variable."
            )
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, **params: Any) -> Any:
        """Perform an authenticated GET request and return parsed JSON."""
        url = f"{STRAVA_API_BASE}/{path.lstrip('/')}"
        response = self._session.get(url, params=params, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_athlete(self) -> dict[str, Any]:
        """Return the authenticated athlete's profile."""
        return self._get("/athlete")

    def get_activities(self, page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
        """Return a list of the athlete's recent activities.

        Parameters
        ----------
        page:
            Page number (1-indexed).
        per_page:
            Number of activities per page (max 200).
        """
        return self._get("/athlete/activities", page=page, per_page=per_page)

    def get_activity(self, activity_id: int) -> dict[str, Any]:
        """Return detailed information for a single activity.

        Parameters
        ----------
        activity_id:
            The numeric Strava activity identifier.
        """
        return self._get(f"/activities/{activity_id}")

    def get_activity_streams(
        self,
        activity_id: int,
        stream_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return time-series data streams for an activity.

        Parameters
        ----------
        activity_id:
            The numeric Strava activity identifier.
        stream_types:
            List of stream keys to request, e.g.
            ``["heartrate", "time", "distance", "watts"]``.
            Defaults to a standard set of streams.
        """
        default_streams = ["time", "distance", "heartrate", "cadence", "watts", "altitude"]
        keys = ",".join(stream_types or default_streams)
        return self._get(
            f"/activities/{activity_id}/streams",
            keys=keys,
            key_by_type=True,
        )
