#!/usr/bin/env python3
"""Recalculate legacy training load for activities that don't have it set.

Reads athlete profile and all activity metrics from the database — no Strava
API calls required.  Safe to run multiple times; skips activities that already
have a training_load value.

Run from the project root with the virtual environment activated::

    python scripts/recalculate_load.py

Options
-------
--all
    Recalculate every activity, not just those missing a training_load.
--dry-run
    Print what would be updated without writing to the database.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_database_url  # noqa: F401 (loads .env)
from src.database.models import Base, Activity, Athlete
from src.database.session import get_session, get_engine
from src.algorithms.training_load import calculate_training_load, ActivityMetrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recalculate legacy training load for activities missing it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--all", action="store_true", dest="recalc_all",
        help="Recalculate all activities, not just those with missing load.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print changes without writing to the database.",
    )
    args = parser.parse_args()

    Base.metadata.create_all(get_engine())

    with get_session() as session:
        athlete = session.query(Athlete).first()
        if athlete:
            logger.info(
                "Athlete: max_hr=%s  resting_hr=%s",
                athlete.max_heart_rate, athlete.resting_heart_rate,
            )
        else:
            logger.warning("No athlete profile found — using algorithm defaults.")

        query = session.query(Activity)
        if not args.recalc_all:
            query = query.filter(Activity.training_load.is_(None))

        activities = query.order_by(Activity.start_date_local).all()
        logger.info(
            "Found %d activit%s to process.",
            len(activities), "y" if len(activities) == 1 else "ies",
        )

        updated = 0
        for activity in activities:
            metrics = ActivityMetrics(
                moving_time=activity.moving_time or 0,
                sport_type=activity.sport_type or "Unknown",
                average_heartrate=activity.average_heartrate,
                max_heartrate=athlete.max_heart_rate if athlete else None,
                resting_heart_rate=athlete.resting_heart_rate if athlete else None,
                distance=activity.distance or 0.0,
                total_elevation_gain=activity.total_elevation_gain,
                average_watts=activity.average_watts,
            )
            new_load = calculate_training_load(metrics)
            old_load = activity.training_load

            print(
                f"  {(activity.start_date_local or '').isoformat()[:10]}  "
                f"{activity.sport_type:<14s}  {activity.name}  "
                f"load: {old_load} → {new_load}"
            )

            if not args.dry_run:
                activity.training_load = new_load
                updated += 1

        if args.dry_run:
            logger.info("Dry run — no changes written.")
        else:
            logger.info("Updated %d activit%s.", updated, "y" if updated == 1 else "ies")


if __name__ == "__main__":
    main()
