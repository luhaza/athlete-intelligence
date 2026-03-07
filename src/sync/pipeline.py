"""Strava activity sync pipeline.

This module is the core of the sync system. It fetches an activity (and its
streams and laps) from the Strava API, upserts all records into the database,
then calculates and stores training load scores.

Usage
-----
Single activity::

    from src.sync.pipeline import sync_activity
    from src.strava.client import StravaClient
    from src.database.session import get_session

    client = StravaClient()
    with get_session() as session:
        result = sync_activity(client, activity_id=12345678, session=session)
        print(result)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.strava.client import StravaClient
from src.database.models import Activity, ActivityStream, ActivityLap, Athlete
from src.algorithms.training_load import calculate_training_load, ActivityMetrics
from src.algorithms.advanced_training_load import (
    calculate_advanced_training_load,
    StreamData,
)

logger = logging.getLogger(__name__)

# How long an athlete profile row is considered fresh before re-fetching from Strava.
# During backfill this means get_athlete() is called once per run, not once per activity.
_ATHLETE_REFRESH_SECS = 86_400  # 24 hours


@dataclass
class SyncResult:
    """Result of a single activity sync operation."""

    strava_activity_id: int
    training_load: float | None
    advanced_load: float | None
    streams_synced: list[str] = field(default_factory=list)
    laps_synced: int = 0
    is_new: bool = True  # True = newly created, False = updated

    def __str__(self) -> str:
        status = "created" if self.is_new else "updated"
        adv = f"{self.advanced_load:.1f}" if self.advanced_load is not None else "n/a"
        return (
            f"Activity {self.strava_activity_id} [{status}] — "
            f"load={self.training_load} advanced={adv} "
            f"streams={self.streams_synced} laps={self.laps_synced}"
        )


def sync_activity(
    client: StravaClient,
    activity_id: int,
    session: Session,
) -> SyncResult:
    """Fetch one Strava activity and sync it to the database.

    Steps:

    1. Fetch full activity detail from Strava.
    2. Ensure the athlete record exists (fetches from Strava on first encounter).
    3. Upsert Activity row.
    4. Fetch and upsert streams (best-effort; 404 means no streams recorded).
    5. Fetch and upsert laps (best-effort; 404 means no laps recorded).
    6. Calculate legacy TRIMP and advanced training load.
    7. Persist load scores back to the Activity row.

    Parameters
    ----------
    client:
        Authenticated StravaClient instance.
    activity_id:
        Strava activity ID to sync.
    session:
        SQLAlchemy session. The caller is responsible for commit/rollback
        (``get_session()`` context manager handles this automatically).

    Returns
    -------
    SyncResult
        Summary of what was synced and the computed load scores.
    """
    logger.info("Syncing activity %s", activity_id)

    # Stage 1: Fetch full activity detail
    activity_data = client.get_activity(activity_id)

    # Stage 2: Ensure the athlete row exists in the DB
    strava_athlete_id = activity_data["athlete"]["id"]
    athlete = _ensure_athlete(client, strava_athlete_id, session)

    # Stage 3: Upsert activity
    activity, is_new = _upsert_activity(activity_data, session)

    # Stage 4: Streams (best-effort — manual activities never have streams;
    # skip the API call entirely to avoid a guaranteed 404)
    streams_synced: list[str] = []
    streams_response: dict = {}
    if not activity_data.get("manual", False):
        try:
            streams_response = client.get_activity_streams(activity_id)
            streams_synced = _upsert_streams(activity_id, streams_response, session)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.debug("No streams available for activity %s", activity_id)
            else:
                raise

    # Stage 5: Laps (best-effort)
    laps_count = 0
    try:
        laps_data = client.get_activity_laps(activity_id)
        laps_count = _upsert_laps(activity_id, laps_data, session)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            logger.debug("No laps available for activity %s", activity_id)
        else:
            raise

    # Stage 6 + 7: Calculate load scores and persist them
    training_load, advanced_load, zone_distribution = _calculate_load(
        activity, athlete, streams_response
    )
    activity.training_load = training_load
    activity.advanced_load = advanced_load
    activity.zone_distribution = zone_distribution

    logger.info(
        "Synced activity %s — load=%.1f advanced=%s streams=%s laps=%d",
        activity_id,
        training_load or 0.0,
        f"{advanced_load:.1f}" if advanced_load is not None else "n/a",
        streams_synced,
        laps_count,
    )

    return SyncResult(
        strava_activity_id=activity_id,
        training_load=training_load,
        advanced_load=advanced_load,
        streams_synced=streams_synced,
        laps_synced=laps_count,
        is_new=is_new,
    )


# ---------------------------------------------------------------------------
# Stage 2: Athlete upsert
# ---------------------------------------------------------------------------

def _ensure_athlete(
    client: StravaClient,
    strava_athlete_id: int,
    session: Session,
) -> Athlete | None:
    """Return the Athlete DB row, creating or refreshing it as needed.

    * First encounter: fetches from Strava and inserts.
    * Subsequent calls within ``_ATHLETE_REFRESH_SECS``: returns the cached row
      without an extra API call (important during bulk backfill).
    * Stale row (> 24 h): re-fetches and updates in place.
    * Concurrent insert race: uses a savepoint so an IntegrityError from a
      parallel worker doesn't poison the outer transaction.
    """
    athlete = (
        session.query(Athlete)
        .filter(Athlete.strava_athlete_id == strava_athlete_id)
        .first()
    )

    if athlete is not None:
        # Return early if the cached profile is still fresh
        updated = athlete.updated_at
        if updated is not None:
            # Normalise to naive UTC for comparison regardless of DB driver behaviour
            if updated.tzinfo is not None:
                updated = updated.replace(tzinfo=None)
            if (datetime.utcnow() - updated).total_seconds() < _ATHLETE_REFRESH_SECS:
                return athlete

    # Fetch from Strava (new athlete or stale profile)
    logger.info("Fetching athlete profile for strava_id=%s", strava_athlete_id)
    profile = client.get_athlete()

    if athlete is None:
        # Use a savepoint so a concurrent INSERT by another worker doesn't
        # roll back the entire outer transaction on IntegrityError.
        try:
            with session.begin_nested():
                athlete = Athlete(
                    strava_athlete_id=profile["id"],
                    username=profile.get("username"),
                    firstname=profile.get("firstname"),
                    lastname=profile.get("lastname"),
                )
                session.add(athlete)
                session.flush()
            return athlete
        except IntegrityError:
            # A concurrent worker beat us — fetch their row instead
            return (
                session.query(Athlete)
                .filter(Athlete.strava_athlete_id == strava_athlete_id)
                .one()
            )
    else:
        # Update stale existing athlete in place
        athlete.username = profile.get("username")
        athlete.firstname = profile.get("firstname")
        athlete.lastname = profile.get("lastname")
        session.flush()
        return athlete


# ---------------------------------------------------------------------------
# Stage 3: Activity upsert
# ---------------------------------------------------------------------------

def _upsert_activity(data: dict, session: Session) -> tuple[Activity, bool]:
    """Create or update an Activity row. Returns ``(activity, is_new)``."""
    strava_id = data["id"]
    activity = (
        session.query(Activity)
        .filter(Activity.strava_activity_id == strava_id)
        .first()
    )
    is_new = activity is None
    if is_new:
        activity = Activity(strava_activity_id=strava_id)
        session.add(activity)

    activity.strava_athlete_id = data["athlete"]["id"]
    activity.name = data.get("name", "")
    activity.description = data.get("description")
    activity.sport_type = data.get("sport_type") or data.get("type", "Unknown")
    activity.workout_type = data.get("workout_type")
    activity.start_date = _parse_dt(data.get("start_date"))
    activity.start_date_local = _parse_dt(data.get("start_date_local"))
    activity.timezone = data.get("timezone")
    activity.elapsed_time = data.get("elapsed_time", 0)
    activity.moving_time = data.get("moving_time", 0)
    activity.distance = data.get("distance", 0.0)
    activity.total_elevation_gain = data.get("total_elevation_gain")
    activity.elev_high = data.get("elev_high")
    activity.elev_low = data.get("elev_low")
    activity.average_speed = data.get("average_speed")
    activity.max_speed = data.get("max_speed")
    activity.average_heartrate = data.get("average_heartrate")
    activity.max_heartrate = data.get("max_heartrate")
    activity.average_cadence = data.get("average_cadence")
    activity.average_watts = data.get("average_watts")
    activity.max_watts = data.get("max_watts")
    activity.weighted_average_watts = data.get("weighted_average_watts")
    activity.device_watts = data.get("device_watts")
    activity.calories = data.get("calories")
    activity.suffer_score = data.get("suffer_score")
    activity.gear_id = data.get("gear_id")
    activity.trainer = data.get("trainer", False)
    activity.commute = data.get("commute", False)
    activity.manual = data.get("manual", False)
    activity.private = data.get("private", False)

    session.flush()
    return activity, is_new


# ---------------------------------------------------------------------------
# Stage 4: Streams upsert
# ---------------------------------------------------------------------------

def _upsert_streams(
    strava_activity_id: int,
    streams_response: dict,
    session: Session,
) -> list[str]:
    """Upsert ActivityStream rows. Returns list of stream types synced."""
    # Bulk-fetch all existing stream rows for this activity in one query
    # instead of issuing one SELECT per stream type (N+1 problem).
    existing_map: dict[str, ActivityStream] = {
        s.stream_type: s
        for s in session.query(ActivityStream).filter(
            ActivityStream.strava_activity_id == strava_activity_id
        ).all()
    }

    synced: list[str] = []
    for stream_type, stream_obj in streams_response.items():
        data = stream_obj.get("data")
        if data is None:
            continue

        existing = existing_map.get(stream_type)
        if existing:
            existing.data = data
            existing.original_size = stream_obj.get("original_size")
            existing.resolution = stream_obj.get("resolution")
            existing.series_type = stream_obj.get("series_type")
        else:
            session.add(ActivityStream(
                strava_activity_id=strava_activity_id,
                stream_type=stream_type,
                data=data,
                original_size=stream_obj.get("original_size"),
                resolution=stream_obj.get("resolution"),
                series_type=stream_obj.get("series_type"),
            ))
        synced.append(stream_type)

    session.flush()
    return synced


# ---------------------------------------------------------------------------
# Stage 5: Laps upsert
# ---------------------------------------------------------------------------

def _upsert_laps(
    strava_activity_id: int,
    laps_data: list[dict],
    session: Session,
) -> int:
    """Delete existing laps and re-insert from Strava data. Returns lap count."""
    session.query(ActivityLap).filter(
        ActivityLap.strava_activity_id == strava_activity_id
    ).delete()

    for lap in laps_data:
        session.add(ActivityLap(
            strava_activity_id=strava_activity_id,
            lap_index=lap.get("lap_index", 1),
            name=lap.get("name"),
            elapsed_time=lap.get("elapsed_time", 0),
            moving_time=lap.get("moving_time", 0),
            start_date=_parse_dt(lap.get("start_date")),
            start_date_local=_parse_dt(lap.get("start_date_local")),
            distance=lap.get("distance", 0.0),
            total_elevation_gain=lap.get("total_elevation_gain"),
            average_speed=lap.get("average_speed"),
            max_speed=lap.get("max_speed"),
            average_heartrate=lap.get("average_heartrate"),
            max_heartrate=lap.get("max_heartrate"),
            average_cadence=lap.get("average_cadence"),
            average_watts=lap.get("average_watts"),
            lap_type=lap.get("lap_trigger"),
        ))

    session.flush()
    return len(laps_data)


# ---------------------------------------------------------------------------
# Stage 6: Load calculation
# ---------------------------------------------------------------------------

def _calculate_load(
    activity: Activity,
    athlete: Athlete | None,
    streams_response: dict,
) -> tuple[float | None, float | None, dict | None]:
    """Compute legacy and advanced training load scores.

    Returns
    -------
    (training_load, advanced_load, zone_distribution)
        ``advanced_load`` and ``zone_distribution`` are ``None`` when no
        heartrate stream is available.
    """
    # Legacy load — always computable, picks best method automatically
    metrics = ActivityMetrics(
        moving_time=activity.moving_time or 0,
        sport_type=activity.sport_type or "Unknown",
        average_heartrate=activity.average_heartrate,
        max_heartrate=activity.max_heartrate,
        resting_heart_rate=athlete.resting_heart_rate if athlete else None,
        distance=activity.distance or 0.0,
        total_elevation_gain=activity.total_elevation_gain,
        average_watts=activity.average_watts,
    )
    training_load = calculate_training_load(metrics)

    # Advanced load — requires heartrate stream
    heartrate_data = streams_response.get("heartrate", {}).get("data")
    if not heartrate_data:
        return training_load, None, None

    streams = StreamData(
        heartrate=heartrate_data,
        time=streams_response.get("time", {}).get("data"),
        altitude=streams_response.get("altitude", {}).get("data"),
        distance=streams_response.get("distance", {}).get("data"),
        velocity_smooth=streams_response.get("velocity_smooth", {}).get("data"),
        watts=streams_response.get("watts", {}).get("data"),
        cadence=streams_response.get("cadence", {}).get("data"),
    )

    max_hr = (athlete.max_heart_rate if athlete and athlete.max_heart_rate else None) or 190
    resting_hr = (athlete.resting_heart_rate if athlete and athlete.resting_heart_rate else None) or 60

    try:
        result = calculate_advanced_training_load(streams, max_hr=max_hr, resting_hr=resting_hr)
        return training_load, result.total_load, result.time_in_zones
    except ValueError as exc:
        logger.warning(
            "Advanced load calculation failed for activity %s: %s",
            activity.strava_activity_id,
            exc,
        )
        return training_load, None, None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(s: str | None) -> datetime | None:
    """Parse a Strava ISO 8601 datetime string to a naive datetime."""
    if not s:
        return None
    # Strava uses "Z" suffix; normalize for broad Python version compatibility
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
