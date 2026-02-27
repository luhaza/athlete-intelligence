# athlete-intelligence
Smarter artificial intelligence for running.

## Overview

This project connects to the Strava API, stores athlete activities in a local
database, and calculates a **training load** (strain) score for each activity
to power insight generation.

## Project structure

```
athlete-intelligence/
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
├── src/
│   ├── strava/
│   │   └── client.py             # Strava v3 API client
│   ├── database/
│   │   └── models.py             # SQLAlchemy ORM models (schema)
│   └── algorithms/
│       └── training_load.py      # Training load / strain algorithm
└── tests/
    ├── test_strava_client.py
    ├── test_models.py
    └── test_training_load.py
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # then add your STRAVA_ACCESS_TOKEN
```

`python-dotenv` is included in the dependencies. Import `src.config` (or call
`dotenv.load_dotenv()`) at the start of your script so that variables in `.env`
are loaded into the process environment before constructing any client or engine.

## 1 — Strava API (`src/strava/client.py`)

`StravaClient` wraps the Strava v3 REST API using an existing OAuth access
token (no OAuth flow required):

```python
import src.config  # loads .env into os.environ
from src.strava.client import StravaClient

client = StravaClient(access_token="<your_token>")  # or set STRAVA_ACCESS_TOKEN

athlete      = client.get_athlete()
acts         = client.get_activities(per_page=50)
activity_id  = acts[0]["id"]  # example: use the ID of the most recent activity
detail       = client.get_activity(activity_id)
streams      = client.get_activity_streams(activity_id, ["heartrate", "time"])
```

## 2 — Database schema (`src/database/models.py`)

Two SQLAlchemy models backed by SQLite (or any SQLAlchemy-compatible DB):

| Table | Key columns |
|---|---|
| `athletes` | `strava_athlete_id`, `firstname`, `lastname`, `resting_heart_rate`, `max_heart_rate` |
| `activities` | `strava_activity_id`, `sport_type`, `moving_time`, `distance`, `total_elevation_gain`, `average_heartrate`, `average_watts`, `suffer_score`, **`training_load`** (computed), … |

```python
from src.database.models import Base, Activity, engine_from_url

engine = engine_from_url()          # uses DATABASE_URL env var or sqlite default
Base.metadata.create_all(engine)
```

## 3 — Training load algorithm (`src/algorithms/training_load.py`)

`calculate_training_load(metrics)` returns a dimensionless strain score.

### Key metrics

| Metric | Unit | Role |
|---|---|---|
| `moving_time` | seconds | Baseline effort duration |
| `average_heartrate` | bpm | Cardiovascular intensity (preferred) |
| `max_heartrate` / `resting_heart_rate` | bpm | HR reserve anchors |
| `average_watts` | W | Direct mechanical work (cycling fallback) |
| `distance` | m | Volume proxy |
| `total_elevation_gain` | m | Adds gradient difficulty bonus |
| `sport_type` | string | Per-sport intensity scaling |

### Algorithm selection

1. **HR available → TRIMP** (Banister 1991): `D × HRr × 0.64 × e^(1.92·HRr)`
2. **Power available (no HR) → power score**: `duration_h × IF² × 100`
3. **Neither → duration × intensity**: speed vs. easy-effort reference

```python
from src.algorithms.training_load import ActivityMetrics, calculate_training_load

score = calculate_training_load(ActivityMetrics(
    moving_time=3600,
    sport_type="Run",
    average_heartrate=155.0,
    max_heartrate=185,
    resting_heart_rate=55,
    distance=12000.0,
    total_elevation_gain=80.0,
))
# → ~58.4
```

## Running tests

```bash
python -m pytest tests/ -v
```

