"""Performance Management Chart (PMC) calculations.

Computes CTL (Chronic Training Load), ATL (Acute Training Load), and
TSB (Training Stress Balance) using exponential weighted moving averages.

    CTL: 42-day EWMA of daily load — "Fitness"
    ATL:  7-day EWMA of daily load — "Fatigue"
    TSB: CTL_yesterday - ATL_yesterday — "Form"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List


CTL_DAYS = 42  # Chronic Training Load time constant
ATL_DAYS = 7   # Acute Training Load time constant


@dataclass
class PMCDay:
    """PMC metrics for a single day."""
    date: date
    daily_load: float
    ctl: float   # Chronic Training Load (fitness)
    atl: float   # Acute Training Load (fatigue)
    tsb: float   # Training Stress Balance (form) = yesterday's CTL - yesterday's ATL


def calculate_pmc(
    daily_loads: Dict[date, float],
    start_date: date,
    end_date: date,
    initial_ctl: float = 0.0,
    initial_atl: float = 0.0,
) -> List[PMCDay]:
    """Calculate PMC metrics for a date range.

    Parameters
    ----------
    daily_loads:
        Map of date → total training load for that day. Missing dates = 0 load.
    start_date:
        First date to include in output.
    end_date:
        Last date to include in output.
    initial_ctl:
        Starting CTL value (default 0).
    initial_atl:
        Starting ATL value (default 0).

    Returns
    -------
    List of PMCDay, one per day in [start_date, end_date].
    """
    ctl = initial_ctl
    atl = initial_atl
    result: List[PMCDay] = []
    current = start_date

    while current <= end_date:
        load = daily_loads.get(current, 0.0)

        # TSB = yesterday's form (CTL - ATL before today's load is applied)
        tsb = ctl - atl

        # Update EWMA
        ctl = ctl + (load - ctl) / CTL_DAYS
        atl = atl + (load - atl) / ATL_DAYS

        result.append(PMCDay(date=current, daily_load=load, ctl=ctl, atl=atl, tsb=tsb))
        current += timedelta(days=1)

    return result


def seed_pmc(
    daily_loads: Dict[date, float],
    up_to: date,
    initial_ctl: float = 0.0,
    initial_atl: float = 0.0,
) -> tuple[float, float]:
    """Compute only the final CTL/ATL values without materialising the full series.

    Use this to efficiently seed the EWMA from historical data before the
    requested window, avoiding a large in-memory list allocation.

    Parameters
    ----------
    daily_loads:
        Map of date → total training load. Missing dates = 0 load.
    up_to:
        Last date to process (inclusive).
    initial_ctl, initial_atl:
        Seed values (default 0).

    Returns
    -------
    (ctl, atl) at the end of ``up_to``.
    """
    if not daily_loads:
        return initial_ctl, initial_atl

    ctl = initial_ctl
    atl = initial_atl
    current = min(daily_loads.keys())

    while current <= up_to:
        load = daily_loads.get(current, 0.0)
        ctl = ctl + (load - ctl) / CTL_DAYS
        atl = atl + (load - atl) / ATL_DAYS
        current += timedelta(days=1)

    return ctl, atl


def compute_trend(snapshots: List[PMCDay], window: int = 7) -> str:
    """Determine CTL trend over the last `window` days.

    Returns 'improving', 'declining', or 'stable'.
    """
    if len(snapshots) < 2:
        return "stable"

    recent = snapshots[-window:] if len(snapshots) >= window else snapshots
    if len(recent) < 2:
        return "stable"

    ctl_delta = recent[-1].ctl - recent[0].ctl
    if ctl_delta > 1.0:
        return "improving"
    elif ctl_delta < -1.0:
        return "declining"
    return "stable"
