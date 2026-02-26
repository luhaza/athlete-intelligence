"""Tests for src/database/models.py."""

import pytest
from datetime import datetime

from sqlalchemy import inspect

from src.database.models import Activity, Athlete, Base, engine_from_url


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
