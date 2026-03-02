"""Tests for src/database/models.py."""

import pytest
from datetime import datetime

from sqlalchemy import inspect

from src.database.models import Activity, ActivityStream, ActivityLap, Athlete, Base, engine_from_url


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    """In-memory SQLite engine for testing."""
    eng = engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


# ---------------------------------------------------------------------------
# Schema / table existence
# ---------------------------------------------------------------------------

def test_tables_created(engine):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "activities" in tables
    assert "athletes" in tables
    assert "activity_streams" in tables
    assert "activity_laps" in tables


def test_activities_columns(engine):
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("activities")}
    required = {
        "id", "strava_activity_id", "strava_athlete_id",
        "name", "sport_type", "start_date", "start_date_local",
        "elapsed_time", "moving_time", "distance",
        "total_elevation_gain", "average_heartrate", "max_heartrate",
        "average_cadence", "average_watts", "calories",
        "suffer_score", "training_load", "trainer", "commute",
        "manual", "private", "created_at", "updated_at",
    }
    assert required <= cols


def test_athletes_columns(engine):
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("athletes")}
    assert {"id", "strava_athlete_id", "firstname", "lastname",
            "resting_heart_rate", "max_heart_rate"} <= cols


# ---------------------------------------------------------------------------
# CRUD round-trip
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_activity():
    return Activity(
        strava_activity_id=111222333,
        strava_athlete_id=9876,
        name="Morning Run",
        sport_type="Run",
        start_date=datetime(2024, 6, 1, 7, 0, 0),
        start_date_local=datetime(2024, 6, 1, 8, 0, 0),
        elapsed_time=3600,
        moving_time=3540,
        distance=10000.0,
        total_elevation_gain=120.0,
        average_heartrate=155.0,
        max_heartrate=175.0,
        average_speed=2.82,
        max_speed=4.1,
        calories=620.0,
        trainer=False,
        commute=False,
        manual=False,
        private=False,
    )


def test_activity_insert_and_query(engine, sample_activity):
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        session.add(sample_activity)
        session.commit()

        fetched = session.query(Activity).filter_by(strava_activity_id=111222333).one()
        assert fetched.name == "Morning Run"
        assert fetched.sport_type == "Run"
        assert fetched.distance == pytest.approx(10000.0)
        assert fetched.average_heartrate == pytest.approx(155.0)


def test_activity_unique_constraint(engine, sample_activity):
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import IntegrityError

    with Session(engine) as session:
        session.add(sample_activity)
        session.commit()

    # Inserting the same strava_activity_id should violate the unique constraint.
    duplicate = Activity(
        strava_activity_id=111222333,
        strava_athlete_id=9876,
        name="Duplicate Run",
        sport_type="Run",
        start_date=datetime(2024, 6, 2, 7, 0, 0),
        start_date_local=datetime(2024, 6, 2, 8, 0, 0),
        elapsed_time=1800,
        moving_time=1800,
        distance=5000.0,
        trainer=False,
        commute=False,
        manual=False,
        private=False,
    )
    with Session(engine) as session:
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()


def test_athlete_insert(engine):
    from sqlalchemy.orm import Session

    athlete = Athlete(
        strava_athlete_id=9876,
        firstname="Jane",
        lastname="Doe",
        resting_heart_rate=55,
        max_heart_rate=185,
    )
    with Session(engine) as session:
        session.add(athlete)
        session.commit()

        fetched = session.query(Athlete).filter_by(strava_athlete_id=9876).one()
        assert fetched.firstname == "Jane"
        assert fetched.max_heart_rate == 185


def test_training_load_field_nullable(engine, sample_activity):
    """training_load is NULL until the algorithm populates it."""
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        session.add(sample_activity)
        session.commit()
        fetched = session.query(Activity).filter_by(strava_activity_id=111222333).one()
        assert fetched.training_load is None


def test_training_load_can_be_set(engine, sample_activity):
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        session.add(sample_activity)
        session.commit()

        fetched = session.query(Activity).filter_by(strava_activity_id=111222333).one()
        fetched.training_load = 87.5
        session.commit()

        updated = session.query(Activity).filter_by(strava_activity_id=111222333).one()
        assert updated.training_load == pytest.approx(87.5)


# ---------------------------------------------------------------------------
# Activity Streams
# ---------------------------------------------------------------------------

def test_activity_stream_insert_and_query(engine, sample_activity):
    """Test creating and querying activity streams."""
    from sqlalchemy.orm import Session
    import json

    with Session(engine) as session:
        session.add(sample_activity)
        session.commit()

        # Add heartrate stream
        hr_stream = ActivityStream(
            strava_activity_id=111222333,
            stream_type="heartrate",
            data=json.dumps([120, 125, 130, 135, 140, 145, 150]),
            original_size=7,
            resolution="high",
            series_type="time"
        )
        session.add(hr_stream)
        session.commit()

        # Query the stream
        fetched = session.query(ActivityStream).filter_by(
            strava_activity_id=111222333,
            stream_type="heartrate"
        ).one()
        
        assert fetched.stream_type == "heartrate"
        data = json.loads(fetched.data)
        assert data == [120, 125, 130, 135, 140, 145, 150]


def test_activity_stream_relationship(engine, sample_activity):
    """Test that activity-stream relationship works."""
    from sqlalchemy.orm import Session
    import json

    with Session(engine) as session:
        session.add(sample_activity)
        
        # Add multiple streams
        hr_stream = ActivityStream(
            strava_activity_id=111222333,
            stream_type="heartrate",
            data=json.dumps([120, 130, 140])
        )
        distance_stream = ActivityStream(
            strava_activity_id=111222333,
            stream_type="distance",
            data=json.dumps([0, 100, 200])
        )
        
        session.add_all([hr_stream, distance_stream])
        session.commit()

        # Query activity and access streams via relationship
        activity = session.query(Activity).filter_by(strava_activity_id=111222333).one()
        assert len(activity.streams) == 2
        stream_types = {s.stream_type for s in activity.streams}
        assert stream_types == {"heartrate", "distance"}


def test_activity_stream_cascade_delete(engine, sample_activity):
    """Test that deleting an activity also deletes its streams."""
    from sqlalchemy.orm import Session
    import json

    with Session(engine) as session:
        session.add(sample_activity)
        
        hr_stream = ActivityStream(
            strava_activity_id=111222333,
            stream_type="heartrate",
            data=json.dumps([120, 130, 140])
        )
        session.add(hr_stream)
        session.commit()

        # Delete the activity
        activity = session.query(Activity).filter_by(strava_activity_id=111222333).one()
        session.delete(activity)
        session.commit()

        # Verify stream is also deleted
        stream_count = session.query(ActivityStream).filter_by(
            strava_activity_id=111222333
        ).count()
        assert stream_count == 0


# ---------------------------------------------------------------------------
# Activity Laps
# ---------------------------------------------------------------------------

def test_activity_lap_insert_and_query(engine, sample_activity):
    """Test creating and querying activity laps."""
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        session.add(sample_activity)
        session.commit()

        # Add a lap
        lap = ActivityLap(
            strava_activity_id=111222333,
            lap_index=1,
            name="Lap 1",
            elapsed_time=600,
            moving_time=595,
            start_date=datetime(2024, 6, 1, 7, 0, 0),
            start_date_local=datetime(2024, 6, 1, 8, 0, 0),
            distance=1000.0,
            average_speed=1.68,
            max_speed=2.0,
            average_heartrate=150.0,
            max_heartrate=165.0,
        )
        session.add(lap)
        session.commit()

        # Query the lap
        fetched = session.query(ActivityLap).filter_by(
            strava_activity_id=111222333,
            lap_index=1
        ).one()
        
        assert fetched.name == "Lap 1"
        assert fetched.distance == pytest.approx(1000.0)
        assert fetched.average_heartrate == pytest.approx(150.0)


def test_activity_lap_relationship(engine, sample_activity):
    """Test that activity-lap relationship works."""
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        session.add(sample_activity)
        
        # Add multiple laps
        lap1 = ActivityLap(
            strava_activity_id=111222333,
            lap_index=1,
            elapsed_time=600,
            moving_time=595,
            start_date=datetime(2024, 6, 1, 7, 0, 0),
            start_date_local=datetime(2024, 6, 1, 8, 0, 0),
            distance=1000.0,
        )
        lap2 = ActivityLap(
            strava_activity_id=111222333,
            lap_index=2,
            elapsed_time=620,
            moving_time=610,
            start_date=datetime(2024, 6, 1, 7, 10, 0),
            start_date_local=datetime(2024, 6, 1, 8, 10, 0),
            distance=1000.0,
        )
        
        session.add_all([lap1, lap2])
        session.commit()

        # Query activity and access laps via relationship
        activity = session.query(Activity).filter_by(strava_activity_id=111222333).one()
        assert len(activity.laps) == 2
        lap_indices = {lap.lap_index for lap in activity.laps}
        assert lap_indices == {1, 2}


def test_activity_lap_cascade_delete(engine, sample_activity):
    """Test that deleting an activity also deletes its laps."""
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        session.add(sample_activity)
        
        lap = ActivityLap(
            strava_activity_id=111222333,
            lap_index=1,
            elapsed_time=600,
            moving_time=595,
            start_date=datetime(2024, 6, 1, 7, 0, 0),
            start_date_local=datetime(2024, 6, 1, 8, 0, 0),
            distance=1000.0,
        )
        session.add(lap)
        session.commit()

        # Delete the activity
        activity = session.query(Activity).filter_by(strava_activity_id=111222333).one()
        session.delete(activity)
        session.commit()

        # Verify lap is also deleted
        lap_count = session.query(ActivityLap).filter_by(
            strava_activity_id=111222333
        ).count()
        assert lap_count == 0
