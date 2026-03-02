#!/usr/bin/env python3
"""Quick script to view database contents."""

from src.database.session import get_session
from src.database.models import Athlete, Activity, ActivityStream, ActivityLap

with get_session() as session:
    # Athlete info
    athlete = session.query(Athlete).first()
    if athlete:
        print("=" * 60)
        print("ATHLETE")
        print("=" * 60)
        print(f"Name: {athlete.firstname} {athlete.lastname}")
        print(f"Username: {athlete.username}")
        print(f"Strava ID: {athlete.strava_athlete_id}")
        print()
    
    # Counts
    activity_count = session.query(Activity).count()
    stream_count = session.query(ActivityStream).count()
    lap_count = session.query(ActivityLap).count()
    
    print("=" * 60)
    print("DATABASE SUMMARY")
    print("=" * 60)
    print(f"Total Activities: {activity_count}")
    print(f"Total Streams: {stream_count}")
    print(f"Total Laps: {lap_count}")
    print()
    
    # Recent activities
    if activity_count > 0:
        print("=" * 60)
        print("RECENT ACTIVITIES (last 10)")
        print("=" * 60)
        activities = session.query(Activity).order_by(
            Activity.start_date.desc()
        ).limit(10).all()
        
        for a in activities:
            date_str = a.start_date.strftime("%Y-%m-%d")
            distance_mi = (a.distance * 0.000621371) if a.distance else 0
            
            # Duration in min:sec format
            if a.moving_time:
                total_seconds = int(a.moving_time)
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                if hours > 0:
                    duration = f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    duration = f"{minutes}:{seconds:02d}"
            else:
                duration = "N/A"
            
            # Calculate pace in min/mile for running, mph for cycling
            if a.average_speed:
                if a.sport_type in ['Run', 'Walk', 'Hike']:
                    # Pace in min/mile (1609.34 meters per mile)
                    pace_min_per_mile = 1609.34 / a.average_speed / 60
                    pace_min = int(pace_min_per_mile)
                    pace_sec = int((pace_min_per_mile - pace_min) * 60)
                    pace = f"{pace_min}:{pace_sec:02d} /mi"
                else:
                    # Speed in mph for cycling, etc.
                    mph = a.average_speed * 2.23694
                    pace = f"{mph:.1f} mph"
            else:
                pace = "N/A"
            
            hr = f"{a.average_heartrate:.0f} bpm" if a.average_heartrate else "N/A"
            
            print(f"\n{date_str} - {a.name}")
            print(f"  Type: {a.sport_type}")
            print(f"  Distance: {distance_mi:.2f} mi")
            print(f"  Duration: {duration}")
            print(f"  Pace: {pace}")
            print(f"  Heart Rate: {hr}")
            
            # Check if streams exist
            stream_count = session.query(ActivityStream).filter_by(
                strava_activity_id=a.strava_activity_id
            ).count()
            if stream_count > 0:
                print(f"  Streams: {stream_count} types")
        
        print("\n" + "=" * 60)
