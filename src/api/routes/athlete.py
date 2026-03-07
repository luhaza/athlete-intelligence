"""Athlete profile endpoints."""

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.schemas import (
    AthleteResponse,
    AthleteStatsResponse,
    AthleteUpdateRequest,
    LoadSummaryResponse,
    LoadPeriodSummary,
    PerformanceDaySnapshot,
    PerformanceResponse,
)
from src.algorithms.performance import calculate_pmc, compute_trend, seed_pmc
from src.database.models import Activity, Athlete


router = APIRouter()


# ---------------------------------------------------------------------------
# GET /athlete
# ---------------------------------------------------------------------------

@router.get("", response_model=AthleteResponse)
async def get_athlete_profile(db: Session = Depends(get_db)):
    """Get athlete profile information."""
    athlete = db.query(Athlete).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete profile not found")
    return AthleteResponse.model_validate(athlete)


# ---------------------------------------------------------------------------
# PATCH /athlete
# ---------------------------------------------------------------------------

_RECALC_BATCH_SIZE = 100


def _recalculate_loads(strava_athlete_id: int) -> None:
    """Re-run training load calculations for all activities after HR config changes.

    Processes activities in batches of ``_RECALC_BATCH_SIZE`` and commits after
    each batch so the session never holds the entire history in memory.
    """
    from src.database.session import get_session
    from src.algorithms.training_load import calculate_training_load, ActivityMetrics
    from src.config.training_zones import DEFAULT_MAX_HR, DEFAULT_RESTING_HR

    with get_session() as session:
        athlete = session.query(Athlete).filter_by(strava_athlete_id=strava_athlete_id).first()
        if not athlete:
            return

        max_hr = athlete.max_heart_rate or DEFAULT_MAX_HR
        resting_hr = athlete.resting_heart_rate or DEFAULT_RESTING_HR

        query = (
            session.query(Activity)
            .filter_by(strava_athlete_id=strava_athlete_id)
            .yield_per(_RECALC_BATCH_SIZE)
        )
        for i, activity in enumerate(query, 1):
            metrics = ActivityMetrics(
                sport_type=activity.sport_type,
                moving_time=activity.moving_time,
                distance=activity.distance or 0.0,
                average_heartrate=activity.average_heartrate,
                average_watts=activity.average_watts,
                total_elevation_gain=activity.total_elevation_gain,
                max_heartrate=max_hr,
                resting_heart_rate=resting_hr,
            )
            activity.training_load = calculate_training_load(metrics)
            if i % _RECALC_BATCH_SIZE == 0:
                session.commit()
        session.commit()  # final partial batch


@router.patch("", response_model=AthleteResponse)
async def update_athlete_profile(
    body: AthleteUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Update athlete HR thresholds and trigger a background recalculation of training loads."""
    athlete = db.query(Athlete).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete profile not found")

    hr_changed = False
    if body.max_heart_rate is not None and body.max_heart_rate != athlete.max_heart_rate:
        athlete.max_heart_rate = body.max_heart_rate
        hr_changed = True
    if body.resting_heart_rate is not None and body.resting_heart_rate != athlete.resting_heart_rate:
        athlete.resting_heart_rate = body.resting_heart_rate
        hr_changed = True

    if hr_changed:
        db.commit()
        db.refresh(athlete)
        # Re-calculate legacy training loads in the background so the endpoint
        # returns immediately rather than blocking on potentially many activities.
        background_tasks.add_task(_recalculate_loads, athlete.strava_athlete_id)

    return AthleteResponse.model_validate(athlete)


# ---------------------------------------------------------------------------
# GET /athlete/stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=AthleteStatsResponse)
async def get_athlete_stats(db: Session = Depends(get_db)):
    """Get aggregate statistics for the athlete."""
    athlete = db.query(Athlete).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete profile not found")

    stats = db.query(
        func.count(Activity.id).label("total_activities"),
        func.sum(Activity.distance).label("total_distance"),
        func.sum(Activity.moving_time).label("total_moving_time"),
        func.sum(Activity.total_elevation_gain).label("total_elevation_gain"),
    ).filter(Activity.strava_athlete_id == athlete.strava_athlete_id).first()

    sport_counts = db.query(
        Activity.sport_type,
        func.count(Activity.id).label("count"),
    ).filter(
        Activity.strava_athlete_id == athlete.strava_athlete_id
    ).group_by(Activity.sport_type).all()

    return {
        "athlete_id": athlete.strava_athlete_id,
        "full_name": " ".join(filter(None, [athlete.firstname, athlete.lastname])) or athlete.username or "Unknown",
        "total_activities": stats.total_activities or 0,
        "total_distance_miles": (stats.total_distance * 0.000621371) if stats.total_distance else 0,
        "total_distance_km": (stats.total_distance / 1000) if stats.total_distance else 0,
        "total_moving_time_hours": (stats.total_moving_time / 3600) if stats.total_moving_time else 0,
        "total_elevation_gain_feet": (stats.total_elevation_gain * 3.28084) if stats.total_elevation_gain else 0,
        "activities_by_sport": {sport: count for sport, count in sport_counts},
    }


# ---------------------------------------------------------------------------
# GET /athlete/performance
# ---------------------------------------------------------------------------

@router.get("/performance", response_model=PerformanceResponse)
async def get_performance(
    start: Optional[str] = Query(None, description="Start date YYYY-MM-DD (default: 90 days ago)"),
    end: Optional[str] = Query(None, description="End date YYYY-MM-DD (default: today)"),
    db: Session = Depends(get_db),
):
    """Return a daily PMC time series (CTL, ATL, TSB) for the given date range.

    CTL (Chronic Training Load) is a 42-day EWMA — a proxy for fitness.
    ATL (Acute Training Load) is a 7-day EWMA — a proxy for fatigue.
    TSB (Training Stress Balance) = CTL_yesterday - ATL_yesterday — a proxy for form.
    """
    athlete = db.query(Athlete).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete profile not found")

    today = date.today()
    try:
        end_date = date.fromisoformat(end) if end else today
        start_date = date.fromisoformat(start) if start else today - timedelta(days=89)
    except ValueError:
        raise HTTPException(status_code=422, detail="Dates must be in YYYY-MM-DD format")

    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start must be before end")

    # Aggregate daily training load in SQL — one row per day across the full
    # history up to end_date so the EWMA seed reflects all past training.
    daily_rows = (
        db.query(
            func.date(Activity.start_date_local).label("activity_date"),
            func.sum(Activity.training_load).label("daily_load"),
        )
        .filter(
            Activity.strava_athlete_id == athlete.strava_athlete_id,
            Activity.start_date_local <= datetime.combine(end_date, datetime.max.time()),
            Activity.training_load.isnot(None),
        )
        .group_by("activity_date")
        .order_by("activity_date")
        .all()
    )

    # func.date() returns a string in SQLite and a date in PostgreSQL
    all_daily: dict[date, float] = {
        (date.fromisoformat(row.activity_date) if isinstance(row.activity_date, str) else row.activity_date): float(row.daily_load or 0.0)
        for row in daily_rows
    }

    # Seed CTL/ATL from history prior to the requested window using the
    # lightweight seed_pmc helper (no full series allocation).
    seed_end = start_date - timedelta(days=1)
    seed_loads = {d: v for d, v in all_daily.items() if d <= seed_end}
    initial_ctl, initial_atl = seed_pmc(seed_loads, seed_end) if seed_loads else (0.0, 0.0)

    # Compute the requested window
    window_loads = {d: v for d, v in all_daily.items() if start_date <= d <= end_date}
    series = calculate_pmc(window_loads, start_date, end_date, initial_ctl, initial_atl)

    trend = compute_trend(series)
    current = series[-1] if series else None

    return PerformanceResponse(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        series=[
            PerformanceDaySnapshot(
                date=day.date.isoformat(),
                daily_load=round(day.daily_load, 2),
                ctl=round(day.ctl, 2),
                atl=round(day.atl, 2),
                tsb=round(day.tsb, 2),
            )
            for day in series
        ],
        current_ctl=round(current.ctl, 2) if current else 0.0,
        current_atl=round(current.atl, 2) if current else 0.0,
        current_tsb=round(current.tsb, 2) if current else 0.0,
        trend=trend,
    )


# ---------------------------------------------------------------------------
# GET /athlete/load/summary
# ---------------------------------------------------------------------------

@router.get("/load/summary", response_model=LoadSummaryResponse)
async def get_load_summary(
    period: str = Query("weekly", pattern="^(weekly|monthly)$", description="'weekly' or 'monthly'"),
    weeks: int = Query(8, ge=1, le=52, description="Number of weeks to return (weekly mode)"),
    months: int = Query(6, ge=1, le=24, description="Number of months to return (monthly mode)"),
    db: Session = Depends(get_db),
):
    """Return aggregated training load, distance, time, and sport breakdown by week or month."""
    athlete = db.query(Athlete).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete profile not found")

    today = date.today()

    if period == "weekly":
        # Build list of (week_start Monday, week_end Sunday) for the last N weeks
        # Week containing today is week 1; we go back `weeks` full weeks.
        current_monday = today - timedelta(days=today.weekday())
        buckets = []
        for i in range(weeks):
            week_start = current_monday - timedelta(weeks=i)
            week_end = week_start + timedelta(days=6)
            iso_year, iso_week, _ = week_start.isocalendar()
            label = f"{iso_year}-W{iso_week:02d}"
            buckets.append((label, week_start, week_end))
        buckets.reverse()  # chronological order

    else:  # monthly
        # Build list of (month_start, month_end) for the last N months
        buckets = []
        year, month = today.year, today.month
        for _ in range(months):
            month_start = date(year, month, 1)
            # last day of month
            if month == 12:
                month_end = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(year, month + 1, 1) - timedelta(days=1)
            label = f"{year}-{month:02d}"
            buckets.append((label, month_start, month_end))
            # go back one month
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        buckets.reverse()

    # Query all activities in the covered date range
    range_start = buckets[0][1]
    range_end = buckets[-1][2]
    activities = db.query(Activity).filter(
        Activity.strava_athlete_id == athlete.strava_athlete_id,
        Activity.start_date_local >= datetime.combine(range_start, datetime.min.time()),
        Activity.start_date_local <= datetime.combine(range_end, datetime.max.time()),
    ).all()

    # Index activities by date
    by_date: dict[date, list[Activity]] = {}
    for act in activities:
        d = act.start_date_local.date()
        by_date.setdefault(d, []).append(act)

    periods: list[LoadPeriodSummary] = []
    for label, bucket_start, bucket_end in buckets:
        total_load = 0.0
        total_distance = 0.0
        total_time = 0
        sport_counts: dict[str, int] = {}

        current = bucket_start
        while current <= bucket_end:
            for act in by_date.get(current, []):
                total_load += act.training_load or 0.0
                total_distance += act.distance or 0.0
                total_time += act.moving_time or 0
                sport_counts[act.sport_type] = sport_counts.get(act.sport_type, 0) + 1
            current += timedelta(days=1)

        periods.append(LoadPeriodSummary(
            period_label=label,
            start_date=bucket_start.isoformat(),
            end_date=bucket_end.isoformat(),
            total_load=round(total_load, 2),
            total_distance_km=round(total_distance / 1000, 2),
            total_moving_time_hours=round(total_time / 3600, 2),
            total_activities=sum(sport_counts.values()),
            activities_by_sport=sport_counts,
        ))

    return LoadSummaryResponse(period=period, periods=periods)
