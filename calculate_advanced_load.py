#!/usr/bin/env python3
"""Calculate advanced training load for all activities with stream data.

This script:
1. Queries all activities that have associated stream data
2. Extracts heartrate and other relevant streams
3. Calculates advanced training load using stream-based algorithms
4. Updates Activity.advanced_load and Activity.zone_distribution fields

Usage
-----
    # Calculate for all activities with streams
    python calculate_advanced_load.py

    # Calculate for specific activity ID
    python calculate_advanced_load.py --activity-id 17570281604

    # Recalculate all (overwrite existing)
    python calculate_advanced_load.py --force

    # Dry run (show what would be calculated)
    python calculate_advanced_load.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

# Add src/ to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from src.database.models import Activity, ActivityStream, Athlete
from src.algorithms.advanced_training_load import (
    calculate_advanced_training_load,
    StreamData,
    result_to_dict,
    DEFAULT_MAX_HR,
    DEFAULT_RESTING_HR,
)


def get_stream_data(session: Session, activity: Activity) -> StreamData:
    """Fetch and parse stream data for an activity.
    
    Parameters
    ----------
    session : Session
        Database session.
    activity : Activity
        Activity to fetch streams for.
    
    Returns
    -------
    StreamData
        Parsed streams with heartrate (required) and optional other streams.
    
    Raises
    ------
    ValueError
        If no heartrate stream found for the activity.
    """
    streams = session.query(ActivityStream).filter_by(
        strava_activity_id=activity.strava_activity_id
    ).all()
    
    stream_dict = {}
    for stream in streams:
        # Parse JSON data
        try:
            data = json.loads(stream.data) if isinstance(stream.data, str) else stream.data
            stream_dict[stream.stream_type] = data
        except (json.JSONDecodeError, TypeError) as e:
            print(f"  ⚠️  Warning: Failed to parse {stream.stream_type} stream: {e}")
            continue
    
    # Heartrate is required
    if 'heartrate' not in stream_dict:
        raise ValueError(f"Activity {activity.strava_activity_id} has no heartrate stream")
    
    return StreamData(
        heartrate=stream_dict.get('heartrate'),
        time=stream_dict.get('time'),
        altitude=stream_dict.get('altitude'),
        distance=stream_dict.get('distance'),
        velocity_smooth=stream_dict.get('velocity_smooth'),
        watts=stream_dict.get('watts'),
        cadence=stream_dict.get('cadence'),
    )


def calculate_for_activity(
    session: Session,
    activity: Activity,
    athlete_max_hr: int,
    athlete_resting_hr: int,
    dry_run: bool = False,
) -> dict:
    """Calculate advanced load for a single activity.
    
    Parameters
    ----------
    session : Session
        Database session.
    activity : Activity
        Activity to calculate load for.
    athlete_max_hr : int
        Athlete's max heart rate.
    athlete_resting_hr : int
        Athlete's resting heart rate.
    dry_run : bool
        If True, don't save to database.
    
    Returns
    -------
    dict
        Calculation result or None if failed.
    """
    try:
        # Get stream data
        streams = get_stream_data(session, activity)
        
        # Calculate advanced load
        result = calculate_advanced_training_load(
            streams=streams,
            max_hr=athlete_max_hr,
            resting_hr=athlete_resting_hr,
        )
        
        print(f"  ✓ {activity.name}")
        print(f"    Total Load: {result.total_load:.1f}")
        print(f"    Base TRIMP: {result.base_trimp:.1f}")
        print(f"    Zone Weighted: {result.zone_weighted_load:.1f}")
        print(f"    Variability: {result.variability_factor:.2f}x")
        print(f"    Anaerobic: {result.anaerobic_load:.1f}")
        print(f"    Elevation: {result.elevation_stress:.1f}")
        print(f"    Zones: Z1={result.zone_percentages[1]}% Z2={result.zone_percentages[2]}% "
              f"Z3={result.zone_percentages[3]}% Z4={result.zone_percentages[4]}% Z5={result.zone_percentages[5]}%")
        
        if not dry_run:
            # Update activity
            activity.advanced_load = result.total_load
            activity.zone_distribution = result_to_dict(result)
            session.commit()
            print(f"    💾 Saved to database")
        else:
            print(f"    🔍 Dry run - not saved")
        
        return result_to_dict(result)
        
    except ValueError as e:
        print(f"  ⚠️  Skipping {activity.name}: {e}")
        return None
    except Exception as e:
        print(f"  ❌ Error processing {activity.name}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Calculate advanced training load from stream data"
    )
    parser.add_argument(
        "--activity-id",
        type=int,
        help="Calculate for specific Strava activity ID only"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recalculate all activities (overwrite existing advanced_load)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show calculations without saving to database"
    )
    
    args = parser.parse_args()
    
    # Connect to database
    db_path = Path(__file__).parent / "athlete_intelligence.db"
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)
    
    engine = create_engine(f"sqlite:///{db_path}")
    session = Session(engine)
    
    # Get athlete HR thresholds
    athlete = session.query(Athlete).first()
    if athlete:
        max_hr = athlete.max_heart_rate or DEFAULT_MAX_HR
        resting_hr = athlete.resting_heart_rate or DEFAULT_RESTING_HR
        print(f"👤 Using athlete HR: max={max_hr} bpm, resting={resting_hr} bpm")
    else:
        max_hr = DEFAULT_MAX_HR
        resting_hr = DEFAULT_RESTING_HR
        print(f"⚠️  No athlete found, using defaults: max={max_hr} bpm, resting={resting_hr} bpm")
    
    # Build query
    if args.activity_id:
        # Specific activity
        activities = session.query(Activity).filter_by(strava_activity_id=args.activity_id).all()
        if not activities:
            print(f"❌ Activity {args.activity_id} not found")
            sys.exit(1)
        print(f"\n📊 Calculating for activity {args.activity_id}...\n")
    else:
        # All activities with streams
        # Find activities that have at least one stream
        activity_ids_with_streams = (
            session.query(ActivityStream.strava_activity_id)
            .distinct()
            .subquery()
        )
        
        query = session.query(Activity).filter(
            Activity.strava_activity_id.in_(activity_ids_with_streams)
        )
        
        if not args.force:
            # Only calculate for activities without advanced_load
            query = query.filter(Activity.advanced_load.is_(None))
        
        activities = query.order_by(Activity.start_date.desc()).all()
        
        if not activities:
            print("✓ All activities with streams already have advanced_load calculated")
            print("  Use --force to recalculate")
            sys.exit(0)
        
        print(f"\n📊 Calculating advanced load for {len(activities)} activities...\n")
    
    # Process each activity
    success_count = 0
    skip_count = 0
    
    for activity in activities:
        result = calculate_for_activity(
            session,
            activity,
            max_hr,
            resting_hr,
            dry_run=args.dry_run,
        )
        
        if result:
            success_count += 1
        else:
            skip_count += 1
        
        print()  # Blank line between activities
    
    # Summary
    print("=" * 60)
    print(f"✓ Completed: {success_count} activities calculated")
    if skip_count > 0:
        print(f"⚠️  Skipped: {skip_count} activities (no heartrate stream)")
    if args.dry_run:
        print(f"🔍 Dry run mode - no changes saved to database")
    
    session.close()


if __name__ == "__main__":
    main()
