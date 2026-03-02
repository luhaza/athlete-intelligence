"""Test database session management."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from contextlib import contextmanager
from src.database.models import Base, Athlete
from datetime import datetime, UTC


@pytest.fixture
def in_memory_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_factory(in_memory_engine):
    """Create a session factory for the in-memory database."""
    return sessionmaker(bind=in_memory_engine)


@contextmanager
def get_test_session(session_factory):
    """Get a test session with automatic cleanup."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_get_engine(in_memory_engine):
    """Test that engine can be created."""
    assert in_memory_engine is not None
    assert hasattr(in_memory_engine, 'connect')


def test_get_session_context_manager(session_factory):
    """Test that session works as a context manager."""
    with get_test_session(session_factory) as session:
        assert isinstance(session, Session)
        assert session.is_active


def test_get_session_creates_athlete(session_factory):
    """Test creating and querying an athlete through session."""
    with get_test_session(session_factory) as session:
        # Create athlete
        athlete = Athlete(
            strava_athlete_id=12345,
            username='test_runner',
            firstname='Test',
            lastname='Runner',
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)
        )
        session.add(athlete)
        session.commit()
        athlete_id = athlete.id
    
    # Query in new session
    with get_test_session(session_factory) as session:
        retrieved = session.query(Athlete).filter_by(id=athlete_id).first()
        assert retrieved is not None
        assert retrieved.username == 'test_runner'
        assert retrieved.firstname == 'Test'


def test_get_session_rollback_on_exception(session_factory):
    """Test that session rolls back on exception."""
    
    # Create an athlete
    with get_test_session(session_factory) as session:
        athlete = Athlete(
            strava_athlete_id=99999,
            username='rollback_test',
            firstname='Rollback',
            lastname='Test',
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)
        )
        session.add(athlete)
        session.commit()
    
    # Try to create duplicate (should fail on unique constraint)
    try:
        with get_test_session(session_factory) as session:
            duplicate = Athlete(
                strava_athlete_id=99999,  # Duplicate!
                username='duplicate',
                firstname='Dup',
                lastname='Licate',
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
            )
            session.add(duplicate)
            session.commit()
    except Exception:
        pass  # Expected to fail
    
    # Verify original athlete still exists and no duplicate
    with get_test_session(session_factory) as session:
        athletes = session.query(Athlete).filter_by(strava_athlete_id=99999).all()
        assert len(athletes) == 1
        assert athletes[0].username == 'rollback_test'


def test_raw_session(session_factory):
    """Test that raw session can be created and used."""
    session = session_factory()
    try:
        assert isinstance(session, Session)
        assert session.is_active
    finally:
        session.close()


def test_raw_session_manual_close(session_factory):
    """Test that raw session must be manually closed."""
    session = session_factory()
    
    # Create athlete
    athlete = Athlete(
        strava_athlete_id=77777,
        username='manual_close',
        firstname='Manual',
        lastname='Close',
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    )
    session.add(athlete)
    session.commit()
    athlete_id = athlete.id
    
    # Must manually close
    session.close()
    
    # Verify athlete exists in new session
    with get_test_session(session_factory) as new_session:
        retrieved = new_session.query(Athlete).filter_by(id=athlete_id).first()
        assert retrieved is not None
        assert retrieved.username == 'manual_close'
