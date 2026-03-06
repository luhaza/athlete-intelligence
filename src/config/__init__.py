"""Configuration module for Athlete Intelligence."""

import os
from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    """Get the database URL from environment or use SQLite default."""
    return os.getenv('DATABASE_URL', 'sqlite:///athlete_intelligence.db')


def is_sqlite() -> bool:
    """Check if the current database is SQLite."""
    return get_database_url().startswith('sqlite://')


def is_postgresql() -> bool:
    """Check if the current database is PostgreSQL."""
    url = get_database_url()
    return url.startswith('postgresql://') or url.startswith('postgres://')
