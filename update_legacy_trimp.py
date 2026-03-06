#!/usr/bin/env python3
"""Update legacy TRIMP scores for activities with advanced load."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database.models import Activity
from algorithms.training_load import calculate_training_load, ActivityMetrics

engine = create_engine('sqlite:///athlete_intelligence.db')
session = Session(engine)

# Calculate legacy TRIMP for activities with advanced_load
activities = session.query(Activity).filter(Activity.advanced_load.isnot(None)).all()

for activity in activities:
    metrics = ActivityMetrics(
        moving_time=activity.moving_time,
        distance=activity.distance,
        total_elevation_gain=activity.total_elevation_gain or 0,
        average_heartrate=activity.average_heartrate,
        average_watts=activity.average_watts,
        sport_type=activity.sport_type,
        max_heartrate=190,
        resting_heart_rate=60,
    )
    
    legacy_load = calculate_training_load(metrics)
    activity.training_load = legacy_load
    
    print(f'{activity.name}:')
    print(f'  Legacy TRIMP: {legacy_load:.1f}')
    print(f'  Advanced Load: {activity.advanced_load:.1f}')
    diff = activity.advanced_load - legacy_load
    pct = (diff / legacy_load * 100) if legacy_load > 0 else 0
    print(f'  Difference: {diff:+.1f} ({pct:+.1f}%)')
    print()

session.commit()
print('✓ Updated legacy TRIMP scores')
