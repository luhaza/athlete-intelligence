#!/usr/bin/env python3
"""Sync Strava data to local database.

This script fetches athlete profile, activities, streams, and laps from
Strava API and stores them in the local database.

Usage:
    python sync_strava.py --full      # Sync all historical data
    python sync_strava.py --incremental  # Sync only new activities
    python sync_strava.py --athlete-only  # Sync only athlete profile
"""

import argparse
import sys
import json
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any

from src.config import get_database_url
from src.strava.client import StravaClient
from src.database.session import get_session
from src.database.models import Athlete, Activity, ActivityStream, ActivityLap


class StravaSync:
    """Syncs Strava data to local database."""
    
    def __init__(self, client: StravaClient, verbose: bool = True):
        """Initialize sync with Strava client.
        
        Args:
            client: Authenticated StravaClient instance
            verbose: If True, print progress messages
        """
        self.client = client
        self.verbose = verbose
        self.stats = {
            'athletes_synced': 0,
            'activities_synced': 0,
            'activities_updated': 0,
            'streams_synced': 0,
            'laps_synced': 0,
            'errors': 0
        }
    
    def log(self, message: str) -> None:
        """Print message if verbose mode is enabled."""
        if self.verbose:
            timestamp = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] {message}")
    
    def sync_athlete(self) -> Optional[Athlete]:
        """Fetch and save athlete profile to database.
        
        Returns:
            Athlete model instance or None if error
        """
        self.log("Fetching athlete profile from Strava...")
        
        try:
            athlete_data = self.client.get_athlete()
            
            with get_session() as session:
                # Check if athlete exists
                athlete = session.query(Athlete).filter_by(
                    strava_athlete_id=athlete_data['id']
                ).first()
                
                now = datetime.now(UTC)
                
                if athlete:
                    # Update existing athlete
                    self.log(f"Updating athlete: {athlete_data.get('firstname')} {athlete_data.get('lastname')}")
                    athlete.username = athlete_data.get('username')
                    athlete.firstname = athlete_data.get('firstname')
                    athlete.lastname = athlete_data.get('lastname')
                    athlete.updated_at = now
                else:
                    # Create new athlete
                    self.log(f"Creating new athlete: {athlete_data.get('firstname')} {athlete_data.get('lastname')}")
                    athlete = Athlete(
                        strava_athlete_id=athlete_data['id'],
                        username=athlete_data.get('username'),
                        firstname=athlete_data.get('firstname'),
                        lastname=athlete_data.get('lastname'),
                        created_at=now,
                        updated_at=now
                    )
                    session.add(athlete)
                
                session.commit()
                self.stats['athletes_synced'] += 1
                self.log(f"✓ Athlete synced: {athlete.firstname} {athlete.lastname}")
                return athlete
                
        except Exception as e:
            self.log(f"✗ Error syncing athlete: {e}")
            self.stats['errors'] += 1
            return None
    
    def sync_activities(self, full: bool = False, limit: Optional[int] = None) -> List[int]:
        """Fetch and save activities to database.
        
        Args:
            full: If True, sync all activities. If False, sync only new ones.
            limit: Maximum number of activities to sync (for testing)
            
        Returns:
            List of synced activity IDs (strava_activity_id)
        """
        # Get most recent activity date for incremental sync
        latest_date = None
        if not full:
            with get_session() as session:
                latest_activity = session.query(Activity).order_by(
                    Activity.start_date.desc()
                ).first()
                
                if latest_activity:
                    latest_date = latest_activity.start_date
                    self.log(f"Incremental sync from: {latest_date}")
                else:
                    self.log("No existing activities, performing full sync")
                    full = True
        
        # Fetch activities from Strava
        self.log(f"Fetching activities from Strava ({'full sync' if full else 'incremental'})...")
        
        synced_activity_ids = []
        page = 1
        total_fetched = 0
        
        try:
            while True:
                # Fetch page of activities
                activities_data = self.client.get_activities(page=page, per_page=100)
                
                if not activities_data:
                    break
                
                self.log(f"Processing page {page} ({len(activities_data)} activities)...")
                
                for activity_data in activities_data:
                    # Check if we've reached limit
                    if limit and total_fetched >= limit:
                        self.log(f"Reached limit of {limit} activities")
                        return synced_activity_ids
                    
                    # Check if activity is newer than latest (for incremental)
                    if not full and latest_date:
                        activity_date = datetime.fromisoformat(
                            activity_data['start_date'].replace('Z', '+00:00')
                        )
                        # Ensure both datetimes are timezone-aware for comparison
                        if latest_date.tzinfo is None:
                            latest_date = latest_date.replace(tzinfo=UTC)
                        if activity_date <= latest_date:
                            self.log(f"Reached existing activities, stopping incremental sync")
                            return synced_activity_ids
                    
                    # Save activity
                    activity_id = self._save_activity(activity_data)
                    if activity_id:
                        synced_activity_ids.append(activity_id)
                        total_fetched += 1
                
                page += 1
                
        except Exception as e:
            self.log(f"✗ Error fetching activities: {e}")
            self.stats['errors'] += 1
        
        return synced_activity_ids
    
    def _save_activity(self, activity_data: Dict[str, Any]) -> Optional[int]:
        """Save a single activity to database.
        
        Args:
            activity_data: Activity data from Strava API
            
        Returns:
            Activity strava_activity_id or None if error
        """
        try:
            with get_session() as session:
                # Check if activity exists
                activity = session.query(Activity).filter_by(
                    strava_activity_id=activity_data['id']
                ).first()
                
                # Parse dates
                start_date = datetime.fromisoformat(
                    activity_data['start_date'].replace('Z', '+00:00')
                )
                start_date_local = datetime.fromisoformat(
                    activity_data['start_date_local'].replace('Z', '+00:00')
                )
                now = datetime.now(UTC)
                
                if activity:
                    # Update existing activity
                    self.log(f"  Updating: {activity_data['name']}")
                    activity.name = activity_data['name']
                    activity.description = activity_data.get('description')
                    activity.sport_type = activity_data['sport_type']
                    activity.workout_type = activity_data.get('workout_type')
                    activity.start_date = start_date
                    activity.start_date_local = start_date_local
                    activity.timezone = activity_data.get('timezone')
                    activity.elapsed_time = activity_data['elapsed_time']
                    activity.moving_time = activity_data['moving_time']
                    activity.distance = activity_data['distance']
                    activity.total_elevation_gain = activity_data.get('total_elevation_gain')
                    activity.elev_high = activity_data.get('elev_high')
                    activity.elev_low = activity_data.get('elev_low')
                    activity.average_speed = activity_data.get('average_speed')
                    activity.max_speed = activity_data.get('max_speed')
                    activity.average_heartrate = activity_data.get('average_heartrate')
                    activity.max_heartrate = activity_data.get('max_heartrate')
                    activity.average_cadence = activity_data.get('average_cadence')
                    activity.average_watts = activity_data.get('average_watts')
                    activity.max_watts = activity_data.get('max_watts')
                    activity.weighted_average_watts = activity_data.get('weighted_average_watts')
                    activity.device_watts = activity_data.get('device_watts', False)
                    activity.calories = activity_data.get('calories')
                    activity.suffer_score = activity_data.get('suffer_score')
                    activity.gear_id = activity_data.get('gear_id')
                    activity.trainer = activity_data.get('trainer', False)
                    activity.commute = activity_data.get('commute', False)
                    activity.manual = activity_data.get('manual', False)
                    activity.private = activity_data.get('private', False)
                    activity.updated_at = now
                    self.stats['activities_updated'] += 1
                else:
                    # Create new activity
                    self.log(f"  Creating: {activity_data['name']}")
                    activity = Activity(
                        strava_activity_id=activity_data['id'],
                        strava_athlete_id=activity_data['athlete']['id'],
                        name=activity_data['name'],
                        description=activity_data.get('description'),
                        sport_type=activity_data['sport_type'],
                        workout_type=activity_data.get('workout_type'),
                        start_date=start_date,
                        start_date_local=start_date_local,
                        timezone=activity_data.get('timezone'),
                        elapsed_time=activity_data['elapsed_time'],
                        moving_time=activity_data['moving_time'],
                        distance=activity_data['distance'],
                        total_elevation_gain=activity_data.get('total_elevation_gain'),
                        elev_high=activity_data.get('elev_high'),
                        elev_low=activity_data.get('elev_low'),
                        average_speed=activity_data.get('average_speed'),
                        max_speed=activity_data.get('max_speed'),
                        average_heartrate=activity_data.get('average_heartrate'),
                        max_heartrate=activity_data.get('max_heartrate'),
                        average_cadence=activity_data.get('average_cadence'),
                        average_watts=activity_data.get('average_watts'),
                        max_watts=activity_data.get('max_watts'),
                        weighted_average_watts=activity_data.get('weighted_average_watts'),
                        device_watts=activity_data.get('device_watts', False),
                        calories=activity_data.get('calories'),
                        suffer_score=activity_data.get('suffer_score'),
                        gear_id=activity_data.get('gear_id'),
                        trainer=activity_data.get('trainer', False),
                        commute=activity_data.get('commute', False),
                        manual=activity_data.get('manual', False),
                        private=activity_data.get('private', False),
                        created_at=now,
                        updated_at=now
                    )
                    session.add(activity)
                    self.stats['activities_synced'] += 1
                
                session.commit()
                return activity.strava_activity_id
                
        except Exception as e:
            self.log(f"  ✗ Error saving activity {activity_data.get('name')}: {e}")
            self.stats['errors'] += 1
            return None
    
    def sync_activity_streams(self, activity: Activity) -> int:
        """Fetch and save activity streams to database.
        
        Args:
            activity: Activity model instance
            
        Returns:
            Number of streams synced
        """
        stream_types = ['time', 'latlng', 'distance', 'altitude', 'heartrate', 
                       'cadence', 'watts', 'temp', 'moving', 'grade_smooth']
        
        try:
            self.log(f"  Fetching streams for: {activity.name}")
            streams_data = self.client.get_activity_streams(
                activity.strava_activity_id,
                stream_types=stream_types
            )
            
            if not streams_data:
                return 0
            
            count = 0
            with get_session() as session:
                now = datetime.now(UTC)
                
                for stream_type, stream_info in streams_data.items():
                    # Check if stream exists
                    stream = session.query(ActivityStream).filter_by(
                        strava_activity_id=activity.strava_activity_id,
                        stream_type=stream_type
                    ).first()
                    
                    # Serialize data as JSON
                    data_json = json.dumps(stream_info.get('data', []))
                    
                    if stream:
                        # Update existing stream
                        stream.data = data_json
                        stream.original_size = stream_info.get('original_size')
                        stream.resolution = stream_info.get('resolution')
                        stream.series_type = stream_info.get('series_type')
                    else:
                        # Create new stream
                        stream = ActivityStream(
                            strava_activity_id=activity.strava_activity_id,
                            stream_type=stream_type,
                            data=data_json,
                            original_size=stream_info.get('original_size'),
                            resolution=stream_info.get('resolution'),
                            series_type=stream_info.get('series_type'),
                            created_at=now
                        )
                        session.add(stream)
                    
                    count += 1
                
                session.commit()
                self.stats['streams_synced'] += count
                self.log(f"    ✓ Synced {count} streams")
                return count
                
        except Exception as e:
            self.log(f"    ✗ Error syncing streams: {e}")
            self.stats['errors'] += 1
            return 0
    
    def sync_activity_laps(self, activity: Activity) -> int:
        """Fetch and save activity laps to database.
        
        Args:
            activity: Activity model instance
            
        Returns:
            Number of laps synced
        """
        try:
            self.log(f"  Fetching laps for: {activity.name}")
            laps_data = self.client.get_activity_laps(activity.strava_activity_id)
            
            if not laps_data:
                return 0
            
            count = 0
            with get_session() as session:
                now = datetime.now(UTC)
                
                for lap_index, lap_info in enumerate(laps_data):
                    # Parse dates
                    start_date = datetime.fromisoformat(
                        lap_info['start_date'].replace('Z', '+00:00')
                    )
                    start_date_local = datetime.fromisoformat(
                        lap_info['start_date_local'].replace('Z', '+00:00')
                    )
                    
                    # Check if lap exists
                    lap = session.query(ActivityLap).filter_by(
                        strava_activity_id=activity.strava_activity_id,
                        lap_index=lap_index
                    ).first()
                    
                    if lap:
                        # Update existing lap
                        lap.name = lap_info.get('name')
                        lap.elapsed_time = lap_info['elapsed_time']
                        lap.moving_time = lap_info['moving_time']
                        lap.start_date = start_date
                        lap.start_date_local = start_date_local
                        lap.distance = lap_info['distance']
                        lap.total_elevation_gain = lap_info.get('total_elevation_gain')
                        lap.average_speed = lap_info.get('average_speed')
                        lap.max_speed = lap_info.get('max_speed')
                        lap.average_heartrate = lap_info.get('average_heartrate')
                        lap.max_heartrate = lap_info.get('max_heartrate')
                        lap.average_cadence = lap_info.get('average_cadence')
                        lap.average_watts = lap_info.get('average_watts')
                        lap.lap_type = lap_info.get('lap_index')  # Strava's lap type indicator
                    else:
                        # Create new lap
                        lap = ActivityLap(
                            strava_activity_id=activity.strava_activity_id,
                            lap_index=lap_index,
                            name=lap_info.get('name'),
                            elapsed_time=lap_info['elapsed_time'],
                            moving_time=lap_info['moving_time'],
                            start_date=start_date,
                            start_date_local=start_date_local,
                            distance=lap_info['distance'],
                            total_elevation_gain=lap_info.get('total_elevation_gain'),
                            average_speed=lap_info.get('average_speed'),
                            max_speed=lap_info.get('max_speed'),
                            average_heartrate=lap_info.get('average_heartrate'),
                            max_heartrate=lap_info.get('max_heartrate'),
                            average_cadence=lap_info.get('average_cadence'),
                            average_watts=lap_info.get('average_watts'),
                            lap_type=lap_info.get('lap_index'),
                            created_at=now
                        )
                        session.add(lap)
                    
                    count += 1
                
                session.commit()
                self.stats['laps_synced'] += count
                self.log(f"    ✓ Synced {count} laps")
                return count
                
        except Exception as e:
            self.log(f"    ✗ Error syncing laps: {e}")
            self.stats['errors'] += 1
            return 0
    
    def sync_all(self, full: bool = False, include_streams: bool = False, 
                 include_laps: bool = False, limit: Optional[int] = None) -> None:
        """Sync all Strava data: athlete, activities, streams, laps.
        
        Args:
            full: If True, sync all historical data
            include_streams: If True, sync activity streams (slower)
            include_laps: If True, sync activity laps (for interval workouts)
            limit: Maximum number of activities to sync
        """
        self.log("=" * 60)
        self.log(f"Starting Strava sync (database: {get_database_url()})")
        self.log("=" * 60)
        
        # Sync athlete profile
        athlete = self.sync_athlete()
        if not athlete:
            self.log("Failed to sync athlete, aborting")
            return
        
        # Sync activities
        activity_ids = self.sync_activities(full=full, limit=limit)
        self.log(f"\n✓ Synced {len(activity_ids)} activities")
        
        # Sync streams if requested
        if include_streams and activity_ids:
            self.log(f"\nSyncing streams for {len(activity_ids)} activities...")
            with get_session() as session:
                activities = session.query(Activity).filter(
                    Activity.strava_activity_id.in_(activity_ids)
                ).all()
                
                for i, activity in enumerate(activities, 1):
                    self.log(f"[{i}/{len(activities)}] {activity.name}")
                    self.sync_activity_streams(activity)
        
        # Sync laps if requested
        if include_laps and activity_ids:
            self.log(f"\nSyncing laps for {len(activity_ids)} activities...")
            with get_session() as session:
                activities = session.query(Activity).filter(
                    Activity.strava_activity_id.in_(activity_ids)
                ).all()
                
                for i, activity in enumerate(activities, 1):
                    self.log(f"[{i}/{len(activities)}] {activity.name}")
                    self.sync_activity_laps(activity)
        
        # 
        # Print summary
        self.print_summary()
    
    def print_summary(self) -> None:
        """Print sync statistics summary."""
        self.log("\n" + "=" * 60)
        self.log("SYNC SUMMARY")
        self.log("=" * 60)
        self.log(f"Athletes synced:     {self.stats['athletes_synced']}")
        self.log(f"Activities created:  {self.stats['activities_synced']}")
        self.log(f"Activities updated:  {self.stats['activities_updated']}")
        self.log(f"Streams synced:      {self.stats['streams_synced']}")
        self.log(f"Laps synced:         {self.stats['laps_synced']}")
        self.log(f"Errors:              {self.stats['errors']}")
        self.log("=" * 60)


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description='Sync Strava data to local database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sync_strava.py --full              # Sync all historical data
  python sync_strava.py --incremental       # Sync only new activities
  python sync_strava.py --athlete-only      # Sync only athlete profile
  python sync_strava.py --full --streams    # Include activity streams (slower)
  python sync_strava.py --limit 10          # Sync only 10 most recent activities
        """
    )
    
    parser.add_argument(
        '--full',
        action='store_true',
        help='Sync all historical activities (default: incremental)'
    )
    parser.add_argument(
        '--incremental',
        action='store_true',
        help='Sync only new activities since last sync'
    )
    parser.add_argument(
        '--athlete-only',
        action='store_true',
        help='Sync only athlete profile, skip activities'
    )
    parser.add_argument(
        '--streams',
        action='store_true',
        help='Include activity streams (heartrate, pace, etc.)'
    )
    parser.add_argument(
        '--laps',
        action='store_true',
        help='Include activity laps (for interval workouts)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of activities to sync'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress messages'
    )
    
    args = parser.parse_args()
    
    # Create Strava client from environment variables
    try:
        client = StravaClient()
    except ValueError as e:
        print(f"Error: {e}")
        print("\nMake sure STRAVA_ACCESS_TOKEN is set in your .env file")
        sys.exit(1)
    
    # Create sync instance
    sync = StravaSync(client, verbose=not args.quiet)
    
    # Execute sync based on arguments
    if args.athlete_only:
        sync.sync_athlete()
        sync.print_summary()
    else:
        full = args.full or not args.incremental
        sync.sync_all(
            full=full,
            include_streams=args.streams,
            include_laps=args.laps,
            limit=args.limit
        )


if __name__ == '__main__':
    main()
