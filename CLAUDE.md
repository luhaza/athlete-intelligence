# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (use venv)
source venv/bin/activate
pip install -r requirements.txt

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_training_load.py -v

# Run a single test by name
python -m pytest tests/test_training_load.py::test_trimp_increases_with_higher_hr -v

# Run the FastAPI server
uvicorn src.api.main:app --reload

# Initialize the database
python -m src.database.init_db
```

## Environment Setup

Copy `.env.example` to `.env` and fill in:
- `STRAVA_ACCESS_TOKEN` — required for Strava API access
- `DATABASE_URL` — defaults to `sqlite:///athlete_intelligence.db`
- `ALLOWED_ORIGINS` — comma-separated CORS origins (defaults to localhost:3000,5173)
- `ENVIRONMENT` — set to `production` to disable `/docs` and `/redoc`

Import `src.config` (or call `dotenv.load_dotenv()`) before constructing any client or DB engine so `.env` is loaded.

## Architecture

The project has three main layers plus a FastAPI backend:

### 1. Strava Layer (`src/strava/`)
- `client.py` — `StravaClient` wraps the Strava v3 REST API using a pre-obtained access token. Methods: `get_athlete()`, `get_activities()`, `get_activity()`, `get_activity_streams()`.
- `get_tokens.py` — OAuth token helpers.
- `playground.py` — scratch/exploration scripts.

### 2. Database Layer (`src/database/`)
- `models.py` — SQLAlchemy ORM with four models: `Athlete`, `Activity`, `ActivityStream`, `ActivityLap`. All distance/speed stored in SI units (metres, m/s). `Activity.training_load` holds the legacy TRIMP score; `Activity.advanced_load` holds the stream-based score; `Activity.zone_distribution` holds a JSON dict of time-in-zones.
- `session.py` — `get_session()` context manager for DB sessions.
- `init_db.py` — creates tables via `Base.metadata.create_all()`.

### 3. Algorithms Layer (`src/algorithms/`)
- `training_load.py` — Aggregate-based algorithm. `calculate_training_load(ActivityMetrics)` dispatches to TRIMP (when HR available), power-based score, or duration×intensity fallback. `SPORT_FACTORS` dict scales load per sport type. Elevation adds up to 20% bonus.
- `advanced_training_load.py` — Stream-based algorithm. `calculate_advanced_training_load(StreamData)` blends six components: instantaneous TRIMP (40%), zone-weighted load (30%), anaerobic contribution (20%), elevation stress (10%), then applies variability and efficiency multipliers. Returns `AdvancedLoadResult` with full breakdown. Requires heartrate stream; other streams are optional.

### 4. Config Layer (`src/config/`)
- `training_zones.py` — Central source for HR zone definitions (`DEFAULT_HR_ZONES`: 5 zones with lower/upper % of max HR and stress weight), physiological defaults, and `get_hr_zones()`/`get_athlete_thresholds()` functions. Currently single-user MVP; per-athlete zones are stubbed out for a future Phase 8.

### 5. FastAPI Layer (`src/api/`)
- `main.py` — App setup: rate limiting via `slowapi` (200/hr, 50/min), CORS, security headers middleware.
- `routes/activities.py` — `GET /activities`, `GET /activities/{id}`, `GET /activities/{id}/streams`, `GET /activities/{id}/laps`.
- `routes/athlete.py` — `GET /athlete`.
- `routes/training_load.py` — Training load calculation endpoints.
- `schemas.py` — Pydantic v2 response models. `ActivitySummary` has computed fields for `distance_miles`, `distance_km`, `duration_formatted`, `pace_per_mile`, `speed_mph`. `ActivityDetail` extends it with `training_load`.
- `dependencies.py` — `get_db()` dependency for injecting DB sessions.

### Key Data Flow
Strava API → `StravaClient` → store in `Activity`/`ActivityStream` → `calculate_training_load()` or `calculate_advanced_training_load()` → store result back in `Activity.training_load`/`Activity.advanced_load` → serve via FastAPI.

### Training Load Algorithm Selection
The legacy algorithm automatically picks: TRIMP if `average_heartrate` is set, power-based if `average_watts` is set, otherwise duration×intensity. The advanced algorithm always requires a `heartrate` stream.
