"""Tests for src/sync/pipeline.py"""

import pytest
import requests as req_lib
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.models import Base, Athlete, Activity, ActivityStream, ActivityLap
from src.sync.pipeline import (
    sync_activity,
    _ensure_athlete,
    _upsert_activity,
    _upsert_streams,
    _upsert_laps,
    _calculate_load,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Fresh in-memory SQLite session for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_athlete.return_value = {
        "id": 12345,
        "username": "testuser",
        "firstname": "Test",
        "lastname": "Athlete",
    }
    client.get_activity.return_value = {
        "id": 999,
        "athlete": {"id": 12345},
        "name": "Morning Run",
        "sport_type": "Run",
        "start_date": "2024-01-15T10:00:00Z",
        "start_date_local": "2024-01-15T10:00:00Z",
        "elapsed_time": 3600,
        "moving_time": 3500,
        "distance": 10000.0,
        "total_elevation_gain": 50.0,
        "average_heartrate": 155.0,
        "max_heartrate": 175.0,
        "average_speed": 2.857,
        "trainer": False,
        "commute": False,
        "manual": False,
        "private": False,
    }
    client.get_activity_streams.return_value = {
        "heartrate": {
            "data": [150, 155, 160, 155, 150] * 100,
            "original_size": 500,
            "resolution": "high",
            "series_type": "time",
        },
        "time": {
            "data": list(range(500)),
            "original_size": 500,
            "resolution": "high",
            "series_type": "time",
        },
    }
    client.get_activity_laps.return_value = [
        {
            "lap_index": 1,
            "name": "Lap 1",
            "elapsed_time": 600,
            "moving_time": 590,
            "start_date": "2024-01-15T10:00:00Z",
            "start_date_local": "2024-01-15T10:00:00Z",
            "distance": 1000.0,
            "average_heartrate": 155.0,
            "max_heartrate": 170.0,
            "average_speed": 2.857,
            "lap_trigger": "lap_button",
        }
    ]
    return client


# ---------------------------------------------------------------------------
# sync_activity — integration
# ---------------------------------------------------------------------------

def test_sync_activity_creates_new_activity(mock_client, db_session):
    result = sync_activity(mock_client, 999, db_session)
    assert result.strava_activity_id == 999
    assert result.is_new is True
    assert result.training_load is not None
    assert result.training_load > 0
    assert result.laps_synced == 1


def test_sync_activity_returns_advanced_load_with_hr_stream(mock_client, db_session):
    result = sync_activity(mock_client, 999, db_session)
    assert result.advanced_load is not None
    assert result.advanced_load > 0
    assert "heartrate" in result.streams_synced


def test_sync_activity_updates_existing_activity(mock_client, db_session):
    sync_activity(mock_client, 999, db_session)
    db_session.commit()
    result = sync_activity(mock_client, 999, db_session)
    assert result.is_new is False


def test_sync_activity_skips_streams_for_manual_activity(mock_client, db_session):
    mock_client.get_activity.return_value["manual"] = True
    result = sync_activity(mock_client, 999, db_session)
    mock_client.get_activity_streams.assert_not_called()
    assert result.streams_synced == []


def test_sync_activity_handles_streams_404_gracefully(mock_client, db_session):
    response = MagicMock()
    response.status_code = 404
    mock_client.get_activity_streams.side_effect = req_lib.HTTPError(response=response)
    result = sync_activity(mock_client, 999, db_session)
    assert result.streams_synced == []
    assert result.training_load is not None  # legacy load still computed


def test_sync_activity_reraises_non_404_stream_error(mock_client, db_session):
    response = MagicMock()
    response.status_code = 500
    mock_client.get_activity_streams.side_effect = req_lib.HTTPError(response=response)
    with pytest.raises(req_lib.HTTPError):
        sync_activity(mock_client, 999, db_session)


def test_sync_activity_handles_laps_404_gracefully(mock_client, db_session):
    response = MagicMock()
    response.status_code = 404
    mock_client.get_activity_laps.side_effect = req_lib.HTTPError(response=response)
    result = sync_activity(mock_client, 999, db_session)
    assert result.laps_synced == 0


# ---------------------------------------------------------------------------
# _ensure_athlete
# ---------------------------------------------------------------------------

def test_ensure_athlete_creates_new_row(mock_client, db_session):
    athlete = _ensure_athlete(mock_client, 12345, db_session)
    assert athlete.strava_athlete_id == 12345
    assert athlete.firstname == "Test"
    assert athlete.lastname == "Athlete"
    mock_client.get_athlete.assert_called_once()


def test_ensure_athlete_returns_cached_row_within_24h(mock_client, db_session):
    _ensure_athlete(mock_client, 12345, db_session)
    db_session.commit()
    mock_client.get_athlete.reset_mock()
    # Second call — should reuse cached row without hitting Strava
    athlete = _ensure_athlete(mock_client, 12345, db_session)
    assert athlete.strava_athlete_id == 12345
    mock_client.get_athlete.assert_not_called()


def test_ensure_athlete_stores_in_db(mock_client, db_session):
    _ensure_athlete(mock_client, 12345, db_session)
    db_session.commit()
    stored = db_session.query(Athlete).filter_by(strava_athlete_id=12345).first()
    assert stored is not None
    assert stored.username == "testuser"


# ---------------------------------------------------------------------------
# _upsert_activity
# ---------------------------------------------------------------------------

_BASE_ACTIVITY = {
    "id": 42,
    "athlete": {"id": 99},
    "name": "Test Run",
    "sport_type": "Run",
    "start_date": "2024-01-01T08:00:00Z",
    "start_date_local": "2024-01-01T08:00:00Z",
    "elapsed_time": 1800,
    "moving_time": 1750,
    "distance": 5000.0,
    "trainer": False,
    "commute": False,
    "manual": False,
    "private": False,
}


def test_upsert_activity_creates_row(db_session):
    activity, is_new = _upsert_activity(_BASE_ACTIVITY, db_session)
    assert is_new is True
    assert activity.strava_activity_id == 42
    assert activity.name == "Test Run"
    assert activity.sport_type == "Run"


def test_upsert_activity_updates_existing_row(db_session):
    _upsert_activity(_BASE_ACTIVITY, db_session)
    updated = {**_BASE_ACTIVITY, "name": "Updated Run"}
    activity, is_new = _upsert_activity(updated, db_session)
    assert is_new is False
    assert activity.name == "Updated Run"


def test_upsert_activity_falls_back_to_type_field(db_session):
    data = {**_BASE_ACTIVITY, "id": 43}
    del data["sport_type"]
    data["type"] = "Ride"
    activity, _ = _upsert_activity(data, db_session)
    assert activity.sport_type == "Ride"


def test_upsert_activity_parses_start_date(db_session):
    activity, _ = _upsert_activity(_BASE_ACTIVITY, db_session)
    assert activity.start_date is not None
    assert activity.start_date_local is not None


# ---------------------------------------------------------------------------
# _upsert_streams
# ---------------------------------------------------------------------------

def _make_activity(session, strava_activity_id=100):
    """Helper: insert a minimal Activity row."""
    from datetime import datetime
    act = Activity(
        strava_activity_id=strava_activity_id,
        strava_athlete_id=1,
        name="",
        sport_type="Run",
        start_date=datetime(2024, 1, 1),
        start_date_local=datetime(2024, 1, 1),
        elapsed_time=0,
        moving_time=0,
        distance=0.0,
    )
    session.add(act)
    session.flush()
    return act


def test_upsert_streams_inserts_new_rows(db_session):
    _make_activity(db_session, 100)
    streams = {
        "heartrate": {"data": [150, 155], "original_size": 2, "resolution": "high", "series_type": "time"},
    }
    synced = _upsert_streams(100, streams, db_session)
    assert "heartrate" in synced
    row = db_session.query(ActivityStream).filter_by(strava_activity_id=100, stream_type="heartrate").first()
    assert row.data == [150, 155]


def test_upsert_streams_updates_existing_rows(db_session):
    _make_activity(db_session, 101)
    db_session.add(ActivityStream(strava_activity_id=101, stream_type="heartrate", data=[140, 145]))
    db_session.flush()
    _upsert_streams(101, {"heartrate": {"data": [160, 165], "original_size": 2}}, db_session)
    row = db_session.query(ActivityStream).filter_by(strava_activity_id=101).first()
    assert row.data == [160, 165]


def test_upsert_streams_uses_single_select(db_session):
    """Bulk-fetch path: only one SELECT for all stream types."""
    _make_activity(db_session, 102)
    streams = {
        "heartrate": {"data": [150], "original_size": 1},
        "altitude": {"data": [100.0], "original_size": 1},
        "time": {"data": [0], "original_size": 1},
    }
    synced = _upsert_streams(102, streams, db_session)
    assert set(synced) == {"heartrate", "altitude", "time"}
    assert db_session.query(ActivityStream).filter_by(strava_activity_id=102).count() == 3


def test_upsert_streams_skips_null_data(db_session):
    _make_activity(db_session, 103)
    streams = {"heartrate": {"data": None}}
    synced = _upsert_streams(103, streams, db_session)
    assert synced == []


# ---------------------------------------------------------------------------
# _upsert_laps
# ---------------------------------------------------------------------------

_BASE_LAP = {
    "lap_index": 1,
    "elapsed_time": 300,
    "moving_time": 295,
    "start_date": "2024-01-01T08:00:00Z",
    "start_date_local": "2024-01-01T08:00:00Z",
    "distance": 1000.0,
    "lap_trigger": "lap_button",
}


def test_upsert_laps_inserts_laps(db_session):
    _make_activity(db_session, 200)
    count = _upsert_laps(200, [_BASE_LAP], db_session)
    assert count == 1
    lap = db_session.query(ActivityLap).filter_by(strava_activity_id=200).first()
    assert lap.lap_type == "lap_button"


def test_upsert_laps_replaces_existing(db_session):
    _make_activity(db_session, 201)
    _upsert_laps(201, [_BASE_LAP], db_session)
    db_session.flush()
    new_laps = [_BASE_LAP, {**_BASE_LAP, "lap_index": 2, "start_date": "2024-01-01T08:05:00Z", "start_date_local": "2024-01-01T08:05:00Z"}]
    count = _upsert_laps(201, new_laps, db_session)
    assert count == 2
    assert db_session.query(ActivityLap).filter_by(strava_activity_id=201).count() == 2


def test_upsert_laps_lap_type_stored_as_string(db_session):
    """lap_trigger is a string from Strava; must be stored as String, not Integer."""
    _make_activity(db_session, 202)
    _upsert_laps(202, [{**_BASE_LAP, "lap_trigger": "distance"}], db_session)
    lap = db_session.query(ActivityLap).filter_by(strava_activity_id=202).first()
    assert lap.lap_type == "distance"
    assert isinstance(lap.lap_type, str)


# ---------------------------------------------------------------------------
# _calculate_load
# ---------------------------------------------------------------------------

def _mock_activity(**kwargs):
    act = MagicMock()
    act.moving_time = kwargs.get("moving_time", 3600)
    act.sport_type = kwargs.get("sport_type", "Run")
    act.average_heartrate = kwargs.get("average_heartrate", None)
    act.max_heartrate = kwargs.get("max_heartrate", None)
    act.distance = kwargs.get("distance", 10000.0)
    act.total_elevation_gain = kwargs.get("total_elevation_gain", 50.0)
    act.average_watts = kwargs.get("average_watts", None)
    act.strava_activity_id = 1
    return act


def test_calculate_load_without_hr_stream():
    activity = _mock_activity()
    training_load, advanced_load, zone_dist = _calculate_load(activity, None, {})
    assert training_load is not None and training_load > 0
    assert advanced_load is None
    assert zone_dist is None


def test_calculate_load_with_hr_stream():
    activity = _mock_activity(average_heartrate=155.0, max_heartrate=180.0)
    streams_response = {
        "heartrate": {"data": [150] * 3600},
        "time": {"data": list(range(3600))},
    }
    training_load, advanced_load, zone_dist = _calculate_load(activity, None, streams_response)
    assert training_load is not None and training_load > 0
    assert advanced_load is not None and advanced_load > 0
    assert zone_dist is not None


def test_calculate_load_zone_distribution_has_full_breakdown():
    """zone_distribution must store the full result_to_dict output, not just time_in_zones.

    The training load API routes read base_trimp, variability_factor, etc. from
    zone_distribution — storing only time_in_zones would make all those fields None.
    """
    activity = _mock_activity(average_heartrate=155.0, max_heartrate=180.0)
    streams_response = {"heartrate": {"data": [150] * 3600}}
    _, _, zone_dist = _calculate_load(activity, None, streams_response)

    assert "base_trimp" in zone_dist
    assert "zone_weighted_load" in zone_dist
    assert "variability_factor" in zone_dist
    assert "anaerobic_load" in zone_dist
    assert "elevation_stress" in zone_dist
    assert "efficiency_penalty" in zone_dist
    assert "time_in_zones" in zone_dist
    assert "zone_percentages" in zone_dist
