"""Tests for FastAPI routes."""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.api.dependencies import get_db
from src.database.models import Base, Activity, Athlete, ActivityStream, ActivityLap


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def test_engine():
    # StaticPool forces a single shared connection so all sessions (including
    # the one used by the TestClient's thread) see the same in-memory database.
    # check_same_thread=False lets SQLite be used from the TestClient thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def test_session(test_engine):
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(test_session):
    def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_athlete(test_session):
    athlete = Athlete(
        strava_athlete_id=12345,
        firstname="Jane",
        lastname="Doe",
        resting_heart_rate=55,
        max_heart_rate=185,
    )
    test_session.add(athlete)
    test_session.commit()
    return athlete


@pytest.fixture
def sample_activity(test_session):
    activity = Activity(
        strava_activity_id=99999,
        strava_athlete_id=12345,
        name="Morning Run",
        sport_type="Run",
        start_date=datetime(2024, 6, 1, 7, 0, 0),
        start_date_local=datetime(2024, 6, 1, 8, 0, 0),
        elapsed_time=3600,
        moving_time=3540,
        distance=10000.0,
        trainer=False,
        commute=False,
        manual=False,
        private=False,
    )
    test_session.add(activity)
    test_session.commit()
    return activity


@pytest.fixture
def activity_with_load(test_session):
    """Activity with both legacy and advanced training load populated."""
    activity = Activity(
        strava_activity_id=88888,
        strava_athlete_id=12345,
        name="Interval Run",
        sport_type="Run",
        start_date=datetime(2024, 6, 2, 7, 0, 0),
        start_date_local=datetime(2024, 6, 2, 8, 0, 0),
        elapsed_time=3600,
        moving_time=3540,
        distance=12000.0,
        training_load=75.5,
        advanced_load=110.2,
        zone_distribution={
            'base_trimp': 80.0,
            'zone_weighted_load': 95.0,
            'variability_factor': 1.3,
            'anaerobic_load': 15.0,
            'elevation_stress': 2.0,
            'efficiency_penalty': 0.0,
            'time_in_zones': {1: 120, 2: 600, 3: 900, 4: 1200, 5: 720},
            'zone_percentages': {1: 3.3, 2: 16.7, 3: 25.0, 4: 33.3, 5: 20.0},
        },
        trainer=False,
        commute=False,
        manual=False,
        private=False,
    )
    test_session.add(activity)
    test_session.commit()
    return activity


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    def test_root_returns_healthy(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert data["app"] == "Athlete Intelligence API"


# ---------------------------------------------------------------------------
# Activity endpoints
# ---------------------------------------------------------------------------

class TestActivitiesEndpoints:
    def test_list_activities_empty(self, client):
        r = client.get("/activities")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["activities"] == []

    def test_list_activities_returns_activity(self, client, sample_activity):
        r = client.get("/activities")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["activities"][0]["name"] == "Morning Run"
        assert data["activities"][0]["strava_activity_id"] == 99999

    def test_list_activities_pagination(self, client, sample_activity):
        r = client.get("/activities?limit=1&offset=0")
        assert r.status_code == 200
        assert len(r.json()["activities"]) == 1

        r = client.get("/activities?limit=1&offset=1")
        assert r.status_code == 200
        assert len(r.json()["activities"]) == 0

    def test_list_activities_filter_sport_match(self, client, sample_activity):
        r = client.get("/activities?sport_type=Run")
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_list_activities_filter_sport_no_match(self, client, sample_activity):
        r = client.get("/activities?sport_type=Ride")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_list_activities_invalid_sport_type(self, client):
        r = client.get("/activities?sport_type=<script>")
        assert r.status_code == 400

    def test_list_activities_invalid_date_range(self, client):
        r = client.get("/activities?start_date=2024-06-10T00:00:00&end_date=2024-06-01T00:00:00")
        assert r.status_code == 400

    def test_get_activity(self, client, sample_activity):
        r = client.get("/activities/99999")
        assert r.status_code == 200
        assert r.json()["strava_activity_id"] == 99999
        assert r.json()["name"] == "Morning Run"

    def test_get_activity_not_found(self, client):
        r = client.get("/activities/000")
        assert r.status_code == 404

    def test_get_streams_activity_not_found(self, client):
        r = client.get("/activities/000/streams")
        assert r.status_code == 404

    def test_get_streams_empty_returns_200(self, client, sample_activity):
        """Activity with no streams should return 200 with empty streams dict."""
        r = client.get("/activities/99999/streams")
        assert r.status_code == 200
        assert r.json()["streams"] == {}

    def test_get_streams_with_data(self, client, sample_activity, test_session):
        stream = ActivityStream(
            strava_activity_id=99999,
            stream_type="heartrate",
            data=[120, 130, 140, 150],
        )
        test_session.add(stream)
        test_session.commit()

        r = client.get("/activities/99999/streams")
        assert r.status_code == 200
        data = r.json()
        assert "heartrate" in data["streams"]
        assert data["streams"]["heartrate"]["data"] == [120, 130, 140, 150]
        assert data["streams"]["heartrate"]["length"] == 4

    def test_get_streams_filter_by_type(self, client, sample_activity, test_session):
        for stream_type, data in [("heartrate", [140, 150]), ("cadence", [85, 87])]:
            test_session.add(ActivityStream(
                strava_activity_id=99999,
                stream_type=stream_type,
                data=data,
            ))
        test_session.commit()

        r = client.get("/activities/99999/streams?types=heartrate")
        assert r.status_code == 200
        streams = r.json()["streams"]
        assert "heartrate" in streams
        assert "cadence" not in streams

    def test_get_laps_empty(self, client, sample_activity):
        r = client.get("/activities/99999/laps")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_laps_with_data(self, client, sample_activity, test_session):
        lap = ActivityLap(
            strava_activity_id=99999,
            lap_index=1,
            elapsed_time=600,
            moving_time=595,
            start_date=datetime(2024, 6, 1, 7, 0, 0),
            start_date_local=datetime(2024, 6, 1, 8, 0, 0),
            distance=1000.0,
        )
        test_session.add(lap)
        test_session.commit()

        r = client.get("/activities/99999/laps")
        assert r.status_code == 200
        laps = r.json()
        assert len(laps) == 1
        assert laps[0]["lap_index"] == 1
        assert laps[0]["distance"] == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# Athlete endpoints
# ---------------------------------------------------------------------------

class TestAthleteEndpoints:
    def test_get_athlete_not_found(self, client):
        r = client.get("/athlete")
        assert r.status_code == 404

    def test_get_athlete(self, client, sample_athlete):
        r = client.get("/athlete")
        assert r.status_code == 200
        data = r.json()
        assert data["strava_athlete_id"] == 12345
        assert data["full_name"] == "Jane Doe"

    def test_get_athlete_stats_not_found(self, client):
        r = client.get("/athlete/stats")
        assert r.status_code == 404

    def test_get_athlete_stats(self, client, sample_athlete, sample_activity):
        r = client.get("/athlete/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_activities"] == 1
        assert data["activities_by_sport"]["Run"] == 1
        assert data["total_distance_km"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Training load endpoints
# ---------------------------------------------------------------------------

class TestTrainingLoadEndpoints:
    def test_get_training_load_not_found(self, client):
        r = client.get("/activities/000/training-load")
        assert r.status_code == 404

    def test_get_training_load_no_zone_dist(self, client, sample_activity):
        r = client.get("/activities/99999/training-load")
        assert r.status_code == 404

    def test_get_training_load(self, client, activity_with_load):
        r = client.get("/activities/88888/training-load")
        assert r.status_code == 200
        data = r.json()
        assert data["advanced_load"] == pytest.approx(110.2)
        assert data["legacy_trimp"] == pytest.approx(75.5)
        assert data["variability_factor"] == pytest.approx(1.3)
        assert "time_in_zones" in data
        assert "zone_percentages" in data

    def test_compare_training_load_no_data(self, client, sample_activity):
        r = client.get("/activities/99999/training-load/comparison")
        assert r.status_code == 404

    def test_compare_training_load(self, client, activity_with_load):
        r = client.get("/activities/88888/training-load/comparison")
        assert r.status_code == 200
        data = r.json()
        assert data["legacy_trimp"] == pytest.approx(75.5)
        assert data["advanced_load"] == pytest.approx(110.2)
        assert data["difference"] == pytest.approx(34.7, abs=0.1)
        assert data["has_intervals"] is True
