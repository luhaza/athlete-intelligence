#!/usr/bin/env python3
"""Manage database entries (delete, cleanup).

This script provides utilities for managing database records including
deletion of activities, streams, laps, and athletes.

Usage:
    python manage_db.py delete-activity <strava_activity_id>
    python manage_db.py delete-athlete <strava_athlete_id>
    python manage_db.py cleanup-orphans
"""

import argparse
import sys
from typing import Optional

from src.database.session import get_session
from src.database.models import Athlete, Activity, ActivityStream, ActivityLap


def delete_activity(strava_activity_id: int, verbose: bool = True) -> bool:
    """Delete an activity and all associated data.
    
    Args:
        strava_activity_id: Strava activity ID to delete
        verbose: If True, print progress messages
        
    Returns:
        True if activity was deleted, False if not found
    """
    with get_session() as session:
        # Find activity
        activity = session.query(Activity).filter_by(
            strava_activity_id=strava_activity_id
        ).first()
        
        if not activity:
            if verbose:
                print(f"Activity {strava_activity_id} not found")
            return False
        
        activity_name = activity.name
        
        # Delete associated streams
        streams_deleted = session.query(ActivityStream).filter_by(
            strava_activity_id=strava_activity_id
        ).delete()
        
        # Delete associated laps
        laps_deleted = session.query(ActivityLap).filter_by(
            strava_activity_id=strava_activity_id
        ).delete()
        
        # Delete activity
        session.delete(activity)
        session.commit()
        
        if verbose:
            print(f"✓ Deleted activity: {activity_name}")
            print(f"  - {streams_deleted} streams removed")
            print(f"  - {laps_deleted} laps removed")
        
        return True


def delete_athlete(strava_athlete_id: int, verbose: bool = True) -> bool:
    """Delete an athlete and all associated activities.
    
    WARNING: This will delete ALL activities for this athlete!
    
    Args:
        strava_athlete_id: Strava athlete ID to delete
        verbose: If True, print progress messages
        
    Returns:
        True if athlete was deleted, False if not found
    """
    with get_session() as session:
        # Find athlete
        athlete = session.query(Athlete).filter_by(
            strava_athlete_id=strava_athlete_id
        ).first()
        
        if not athlete:
            if verbose:
                print(f"Athlete {strava_athlete_id} not found")
            return False
        
        athlete_name = f"{athlete.firstname} {athlete.lastname}"
        
        # Get all activities for this athlete
        activities = session.query(Activity).filter_by(
            strava_athlete_id=strava_athlete_id
        ).all()
        
        activity_ids = [a.strava_activity_id for a in activities]
        
        # Delete all streams for these activities
        streams_deleted = 0
        laps_deleted = 0
        
        if activity_ids:
            streams_deleted = session.query(ActivityStream).filter(
                ActivityStream.strava_activity_id.in_(activity_ids)
            ).delete(synchronize_session=False)
            
            laps_deleted = session.query(ActivityLap).filter(
                ActivityLap.strava_activity_id.in_(activity_ids)
            ).delete(synchronize_session=False)
        
        # Delete all activities
        activities_deleted = session.query(Activity).filter_by(
            strava_athlete_id=strava_athlete_id
        ).delete()
        
        # Delete athlete
        session.delete(athlete)
        session.commit()
        
        if verbose:
            print(f"✓ Deleted athlete: {athlete_name}")
            print(f"  - {activities_deleted} activities removed")
            print(f"  - {streams_deleted} streams removed")
            print(f"  - {laps_deleted} laps removed")
        
        return True


def cleanup_orphans(verbose: bool = True) -> dict:
    """Remove orphaned streams and laps (no matching activity).
    
    Args:
        verbose: If True, print progress messages
        
    Returns:
        Dictionary with counts of deleted records
    """
    with get_session() as session:
        # Get all activity IDs
        activity_ids = [a.strava_activity_id for a in session.query(Activity).all()]
        
        # Delete streams without matching activities
        orphaned_streams = session.query(ActivityStream).filter(
            ~ActivityStream.strava_activity_id.in_(activity_ids)
        ).delete(synchronize_session=False)
        
        # Delete laps without matching activities
        orphaned_laps = session.query(ActivityLap).filter(
            ~ActivityLap.strava_activity_id.in_(activity_ids)
        ).delete(synchronize_session=False)
        
        session.commit()
        
        if verbose:
            print(f"✓ Cleanup complete:")
            print(f"  - {orphaned_streams} orphaned streams removed")
            print(f"  - {orphaned_laps} orphaned laps removed")
        
        return {
            'streams': orphaned_streams,
            'laps': orphaned_laps
        }


def list_activities(limit: Optional[int] = None, verbose: bool = True) -> None:
    """List activities in the database.
    
    Args:
        limit: Maximum number of activities to show
        verbose: If True, print activity details
    """
    with get_session() as session:
        query = session.query(Activity).order_by(Activity.start_date.desc())
        
        if limit:
            query = query.limit(limit)
        
        activities = query.all()
        
        if not activities:
            print("No activities found in database")
            return
        
        print(f"\nFound {len(activities)} activities:")
        print("-" * 80)
        
        for i, activity in enumerate(activities, 1):
            date = activity.start_date_local.strftime('%Y-%m-%d')
            distance_mi = (activity.distance * 0.000621371) if activity.distance else 0
            duration_min = activity.moving_time / 60 if activity.moving_time else 0
            
            print(f"{i}. ID: {activity.strava_activity_id}")
            print(f"   {date} - {activity.name}")
            print(f"   {distance_mi:.2f} mi, {duration_min:.1f} min")
            print()


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description='Manage database entries',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  delete-activity <id>   Delete activity and associated streams/laps
  delete-athlete <id>    Delete athlete and ALL their activities
  cleanup-orphans        Remove orphaned streams/laps
  list                   List all activities in database

Examples:
  python manage_db.py delete-activity 12345678
  python manage_db.py delete-athlete 9876543
  python manage_db.py cleanup-orphans
  python manage_db.py list --limit 20
        """
    )
    
    parser.add_argument(
        'command',
        choices=['delete-activity', 'delete-athlete', 'cleanup-orphans', 'list'],
        help='Command to execute'
    )
    parser.add_argument(
        'id',
        nargs='?',
        type=int,
        help='Strava ID (required for delete commands)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of results (for list command)'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress messages'
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Skip confirmation prompts'
    )
    
    args = parser.parse_args()
    verbose = not args.quiet
    
    # Execute command
    if args.command == 'delete-activity':
        if not args.id:
            print("Error: Activity ID is required")
            print("Usage: python manage_db.py delete-activity <strava_activity_id>")
            sys.exit(1)
        
        if not args.yes:
            confirm = input(f"Delete activity {args.id} and all associated data? (y/N): ")
            if confirm.lower() != 'y':
                print("Cancelled")
                sys.exit(0)
        
        success = delete_activity(args.id, verbose=verbose)
        sys.exit(0 if success else 1)
    
    elif args.command == 'delete-athlete':
        if not args.id:
            print("Error: Athlete ID is required")
            print("Usage: python manage_db.py delete-athlete <strava_athlete_id>")
            sys.exit(1)
        
        if not args.yes:
            print(f"WARNING: This will delete athlete {args.id} and ALL their activities!")
            confirm = input("Are you sure? (y/N): ")
            if confirm.lower() != 'y':
                print("Cancelled")
                sys.exit(0)
        
        success = delete_athlete(args.id, verbose=verbose)
        sys.exit(0 if success else 1)
    
    elif args.command == 'cleanup-orphans':
        if not args.yes:
            confirm = input("Remove orphaned streams and laps? (y/N): ")
            if confirm.lower() != 'y':
                print("Cancelled")
                sys.exit(0)
        
        cleanup_orphans(verbose=verbose)
        sys.exit(0)
    
    elif args.command == 'list':
        list_activities(limit=args.limit, verbose=verbose)
        sys.exit(0)


if __name__ == '__main__':
    main()
