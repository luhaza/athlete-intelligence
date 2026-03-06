"""Strava API client.

Uses an existing OAuth access token to fetch athlete data and activities
from the Strava v3 API (https://developers.strava.com/docs/reference/).
"""

import os
import time
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
    refresh_token:
        A Strava refresh token for automatic token renewal. When omitted the value
        is read from the ``STRAVA_REFRESH_TOKEN`` environment variable.
    client_id:
        Your Strava application client ID. When omitted the value is read
        from the ``STRAVA_CLIENT_ID`` environment variable.
    client_secret:
        Your Strava application client secret. When omitted the value is read
        from the ``STRAVA_CLIENT_SECRET`` environment variable.
    expires_at:
        Unix timestamp when the access token expires. When omitted the value is read
        from the ``STRAVA_EXPIRES_AT`` environment variable.
    timeout:
        Timeout in seconds for all HTTP requests. Defaults to 10 seconds.
    """

    def __init__(
        self,
        access_token: str | None = None,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        expires_at: int | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._access_token = access_token or os.environ.get("STRAVA_ACCESS_TOKEN")
        self._refresh_token = refresh_token or os.environ.get("STRAVA_REFRESH_TOKEN")
        self._client_id = client_id or os.environ.get("STRAVA_CLIENT_ID")
        self._client_secret = client_secret or os.environ.get("STRAVA_CLIENT_SECRET")
        
        if not self._access_token:
            raise ValueError(
                "A Strava access token must be provided either as an argument "
                "or via the STRAVA_ACCESS_TOKEN environment variable."
            )
        
        # Parse expires_at from environment if available
        expires_at_env = os.environ.get("STRAVA_EXPIRES_AT")
        if expires_at is None and expires_at_env:
            try:
                expires_at = int(expires_at_env)
            except ValueError:
                expires_at = None
        
        self._expires_at = expires_at
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self._access_token}"})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
        if not self._refresh_token:
            raise ValueError(
                "Cannot refresh token: refresh_token is not set. "
                "Please provide STRAVA_REFRESH_TOKEN environment variable."
            )
        if not self._client_id or not self._client_secret:
            raise ValueError(
                "Cannot refresh token: client_id and client_secret are required. "
                "Please provide STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET environment variables."
            )
        
        response = requests.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        
        # Update tokens and expiration
        self._access_token = data["access_token"]
        self._refresh_token = data["refresh_token"]
        self._expires_at = data["expires_at"]
        
        # Update session authorization header
        self._session.headers.update({"Authorization": f"Bearer {self._access_token}"})

    def _ensure_valid_token(self) -> None:
        """Check if token is expired and refresh if necessary."""
        if self._expires_at is None:
            # No expiration info, assume token is valid
            return
        
        # Refresh if token expires in less than 5 minutes
        if time.time() >= (self._expires_at - 300):
            self._refresh_access_token()

    def _get(self, path: str, **params: Any) -> Any:
        """Perform an authenticated GET request and return parsed JSON."""
        self._ensure_valid_token()
        url = f"{STRAVA_API_BASE}/{path.lstrip('/')}"
        response = self._session.get(url, params=params, timeout=self._timeout)
        
        # If we get a 401, the token might be invalid even if not expired
        # Try refreshing once and retry
        if response.status_code == 401 and self._refresh_token:
            self._refresh_access_token()
            # Retry the request with new token
            response = self._session.get(url, params=params, timeout=self._timeout)
        
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_athlete(self) -> dict[str, Any]:
        """Return the authenticated athlete's profile."""
        return self._get("/athlete")

    def get_activities(
        self,
        page: int = 1,
        per_page: int = 30,
        before: int | None = None,
        after: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return a list of the athlete's recent activities.

        Parameters
        ----------
        page:
            Page number (1-indexed).
        per_page:
            Number of activities per page (max 200).
        before:
            Unix timestamp — return only activities started before this time.
            Useful for incremental sync.
        after:
            Unix timestamp — return only activities started after this time.
            Useful for incremental sync.
        """
        if per_page > 200:
            raise ValueError("per_page cannot exceed 200 (Strava API limit).")
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        return self._get("/athlete/activities", **params)

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
            key_by_type="true",  # Strava expects lowercase string, not Python bool
        )

    def get_activity_laps(self, activity_id: int) -> list[dict[str, Any]]:
        """Return lap data for an activity.

        Parameters
        ----------
        activity_id:
            The numeric Strava activity identifier.

        Returns
        -------
        List of lap dictionaries containing lap metrics (distance, time, pace, etc.)
        """
        return self._get(f"/activities/{activity_id}/laps")
