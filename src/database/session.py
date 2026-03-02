"""Database session management.

This module provides a unified way to get database sessions that works
with both SQLite and PostgreSQL. Import get_session() to interact with
the database.

Usage:
    from src.database.session import get_session
    
    with get_session() as session:
        athletes = session.query(Athlete).all()
"""

from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.config import get_database_url


# Create engine (singleton)
_engine = None


def get_engine():
    """Get or create the SQLAlchemy engine.
    
    Returns:
        SQLAlchemy engine instance.
    """
    global _engine
    if _engine is None:
        database_url = get_database_url()
        _engine = create_engine(
            database_url,
            echo=False,  # Set to True for SQL logging
            pool_pre_ping=True,  # Verify connections before using
        )
    return _engine


# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a database session with automatic cleanup.
    
    This is a context manager that ensures the session is properly
    closed after use, even if an exception occurs.
    
    Yields:
        SQLAlchemy Session instance.
        
    Example:
        with get_session() as session:
            athlete = session.query(Athlete).first()
            print(athlete.firstname)
    """
    engine = get_engine()
    SessionLocal.configure(bind=engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_raw_session() -> Session:
    """Get a raw database session without context manager.
    
    WARNING: You must manually close this session when done!
    Prefer using get_session() context manager instead.
    
    Returns:
        SQLAlchemy Session instance.
        
    Example:
        session = get_raw_session()
        try:
            athlete = session.query(Athlete).first()
        finally:
            session.close()
    """
    engine = get_engine()
    SessionLocal.configure(bind=engine)
    return SessionLocal()
