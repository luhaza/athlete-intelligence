"""Initialize the database with all tables.

This script creates all tables defined in models.py using SQLAlchemy.
It works with both SQLite (development) and PostgreSQL (production).

Usage:
    python -m src.database.init_db
"""

import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError

# Import config to load environment variables
from src.config import get_database_url, is_sqlite, is_postgresql

# Import Base to access metadata
from src.database.models import Base, Athlete, Activity, ActivityStream, ActivityLap


def init_database(echo: bool = True) -> bool:
    """Initialize the database with all tables.
    
    Args:
        echo: If True, log all SQL statements to console.
        
    Returns:
        True if successful, False otherwise.
    """
    database_url = get_database_url()
    print(f"Initializing database: {database_url}")
    
    # Determine database type
    if is_sqlite():
        print("Database type: SQLite (development)")
        db_path = database_url.replace('sqlite:///', '')
        if Path(db_path).exists():
            print(f" Database file already exists: {db_path}")
            response = input("Do you want to recreate it? This will DELETE all data! (yes/no): ")
            if response.lower() != 'yes':
                print("Aborted.")
                return False
            Path(db_path).unlink()
            print(f"Deleted existing database: {db_path}")
    elif is_postgresql():
        print("Database type: PostgreSQL (production)")
        print(" Make sure the database exists before running this script.")
        print("    You may need to run: createdb athlete_intelligence")
    else:
        print(f" Unknown database type: {database_url}")
        print("    Supported types: sqlite://, postgresql://")
    
    try:
        # Create engine
        engine = create_engine(database_url, echo=echo)
        
        # Test connection
        with engine.connect() as conn:
            print("✓ Database connection successful")
        
        # Create all tables
        print("\nCreating tables...")
        Base.metadata.create_all(engine)
        
        # Verify tables were created
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"\n✓ Created {len(tables)} tables:")
        for table in tables:
            print(f"  - {table}")
        
        # Verify expected tables exist
        expected_tables = {'athletes', 'activities', 'activity_streams', 'activity_laps'}
        missing_tables = expected_tables - set(tables)
        if missing_tables:
            print(f"\n Warning: Missing expected tables: {missing_tables}")
            return False
        
        print("\n✅ Database initialized successfully!")
        return True
        
    except SQLAlchemyError as e:
        print(f"\n❌ Error initializing database: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False


if __name__ == '__main__':
    # Parse command line arguments
    echo = '--quiet' not in sys.argv and '-q' not in sys.argv
    
    # Initialize database
    success = init_database(echo=echo)
    sys.exit(0 if success else 1)
