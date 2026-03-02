"""Load environment variables from a .env file at startup.

Import this module (or call :func:`load_env`) before constructing any
client or database engine so that variables defined in ``.env`` are
available via ``os.environ``.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    """Get the database URL from environment or use SQLite default.
    
    Returns:
        Database URL for SQLAlchemy. Defaults to SQLite if not specified.
        
    Examples:
        SQLite (development):
            sqlite:///athlete_intelligence.db
        
        PostgreSQL (production):
            postgresql://user:password@localhost:5432/athlete_intelligence
    """
    return os.getenv('DATABASE_URL', 'sqlite:///athlete_intelligence.db')


def is_sqlite() -> bool:
    """Check if the current database is SQLite.
    
    Returns:
        True if using SQLite, False otherwise.
    """
    return get_database_url().startswith('sqlite://')


def is_postgresql() -> bool:
    """Check if the current database is PostgreSQL.
    
    Returns:
        True if using PostgreSQL, False otherwise.
    """
    url = get_database_url()
    return url.startswith('postgresql://') or url.startswith('postgres://')
