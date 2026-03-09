#!/usr/bin/env python3
"""Backfill all historical Strava activities into the database.

Run from the project root with the virtual environment activated::

    python scripts/backfill.py

Options
-------
--after TIMESTAMP
    Only sync activities that started after this Unix timestamp.
    Useful for incremental re-runs (e.g. ``--after 1700000000``).
--before TIMESTAMP
    Only sync activities that started before this Unix timestamp.
--sport-type TYPE
    Only sync activities of this sport type (e.g. ``Run``, ``Ride``).
    Defaults to ``Run``.  Pass an empty string to sync all sport types.
--max N
    Stop after syncing N activities (useful for testing).
--dry-run
    Fetch the activity list but skip all DB writes and load calculation.
--delay SECONDS
    Pause between individual activity fetches (default: 30s).
    Strava's rate limit is 100 requests / 15 min and 1 000 / day.
    Each activity requires ~4 API calls, so 30s keeps well within limits.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Allow running as ``python scripts/backfill.py`` from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import config first — this loads .env via load_dotenv()
from src.config import get_database_url  # noqa: F401 (side-effect: loads .env)

from src.strava.client import StravaClient
from src.database.models import Base, Activity
from src.database.session import get_session, get_engine
from src.sync.pipeline import sync_activity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill Strava activities into the local database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--after", type=int, default=None, metavar="TIMESTAMP",
        help="Only sync activities after this Unix timestamp.",
    )
    parser.add_argument(
        "--before", type=int, default=None, metavar="TIMESTAMP",
        help="Only sync activities before this Unix timestamp.",
    )
    parser.add_argument(
        "--sport-type", type=str, default="Run", metavar="TYPE",
        help="Only sync activities of this sport type (default: Run). Pass '' for all.",
    )
    parser.add_argument(
        "--max", type=int, default=None, dest="max_activities", metavar="N",
        help="Stop after syncing N activities.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List activities without writing to the database.",
    )
    parser.add_argument(
        "--delay", type=float, default=30.0, metavar="SECONDS",
        help="Pause between individual activity syncs (default: 30s).",
    )
    args = parser.parse_args()

    # Ensure all tables exist (create_all is idempotent)
    logger.info("Ensuring database schema is up to date...")
    Base.metadata.create_all(get_engine())

    client = StravaClient()

    total_synced = 0
    total_errors = 0
    page = 1

    sport_filter = args.sport_type.strip() if args.sport_type else ""
    logger.info(
        "Starting backfill — after=%s before=%s sport_type=%r max=%s dry_run=%s",
        args.after, args.before, sport_filter or "all", args.max_activities, args.dry_run,
    )

    while True:
        logger.info("Fetching page %d from Strava...", page)
        activities = client.get_activities(
            page=page,
            per_page=200,
            after=args.after,
            before=args.before,
        )

        if not activities:
            logger.info("No more activities found on page %d.", page)
            break

        logger.info("Page %d: %d activities", page, len(activities))

        for act in activities:
            sport = act.get("sport_type") or act.get("type", "Unknown")
            if sport_filter and sport != sport_filter:
                continue
            activity_id = act["id"]
            name = act.get("name", "Unknown")
            date = (act.get("start_date_local") or "")[:10]

            with get_session() as session:
                exists = session.query(Activity).filter(
                    Activity.strava_activity_id == activity_id
                ).first() is not None

            if exists:
                logger.debug("Skipping already-synced activity %s (%s)", activity_id, name)
                continue

            if args.dry_run:
                print(f"  [dry-run] {date}  {sport_filter or sport:<14s}  {name}  (id={activity_id})")
                total_synced += 1
            else:
                try:
                    with get_session() as session:
                        result = sync_activity(client, activity_id, session)
                    print(f"  {result}")
                    total_synced += 1
                except Exception as exc:
                    logger.error(
                        "Failed to sync activity %s (%s): %s",
                        activity_id, name, exc,
                    )
                    total_errors += 1

            if args.max_activities and total_synced >= args.max_activities:
                break

            if not exists:
                time.sleep(args.delay)

        if args.max_activities and total_synced >= args.max_activities:
            logger.info("Reached --max limit (%d).", args.max_activities)
            break

        page += 1

    logger.info(
        "Backfill complete. Synced: %d  Errors: %d",
        total_synced, total_errors,
    )

    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
