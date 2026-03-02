# Database Setup

This directory contains the database models and initialization scripts for the Athlete Intelligence application.

## Quick Start

### 1. Initialize SQLite Database (Development)

```bash
python -m src.database.init_db
```

This creates `athlete_intelligence.db` in the project root with all tables.

### 2. Use the Database

```python
from src.database.session import get_session
from src.database.models import Athlete, Activity

# Query data
with get_session() as session:
    athletes = session.query(Athlete).all()
    for athlete in athletes:
        print(f"{athlete.firstname} {athlete.lastname}")

# Insert data
with get_session() as session:
    athlete = Athlete(
        strava_athlete_id=12345,
        username='runner123',
        firstname='John',
        lastname='Doe'
    )
    session.add(athlete)
    # Automatically commits on context exit
```

## Database Models

### Athlete
- Stores athlete profile information
- Links to activities via `strava_athlete_id`
- Includes heart rate thresholds for training load calculation

### Activity
- Main table for workout/activity data
- Includes metrics: distance, time, heart rate, power, cadence
- Links to ActivityStream and ActivityLap via `strava_activity_id`

### ActivityStream
- Time-series data for activities (heart rate, pace, power, cadence, etc.)
- Data stored as JSON for flexibility
- Cascade deletes when parent Activity is deleted

### ActivityLap
- Lap/split data for interval workouts
- Stores per-lap metrics (heart rate, pace, power)
- Cascade deletes when parent Activity is deleted

## Configuration

The database URL is controlled by the `DATABASE_URL` environment variable in `.env`:

```bash
# SQLite (development)
DATABASE_URL=sqlite:///athlete_intelligence.db

# PostgreSQL (production)
DATABASE_URL=postgresql://user:password@localhost:5432/athlete_intelligence
```

## Switching to PostgreSQL

See [POSTGRESQL_MIGRATION.md](../../POSTGRESQL_MIGRATION.md) for detailed instructions.

**Quick switch:**

1. Install PostgreSQL driver:
   ```bash
   pip install psycopg2-binary
   ```

2. Update `.env`:
   ```bash
   DATABASE_URL=postgresql://user:password@localhost:5432/athlete_intelligence
   ```

3. Initialize PostgreSQL database:
   ```bash
   python -m src.database.init_db
   ```

That's it! The same code works with both SQLite and PostgreSQL.

## Files

- `models.py` - SQLAlchemy ORM models (Athlete, Activity, ActivityStream, ActivityLap)
- `session.py` - Database session management with context managers
- `init_db.py` - Database initialization script

## Testing

Tests use in-memory SQLite databases and don't affect the real database:

```bash
pytest tests/test_models.py -v      # Test models
pytest tests/test_session.py -v     # Test session management
```
