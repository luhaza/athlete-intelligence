"""Unit tests for the PMC (Performance Management Chart) algorithm."""

from datetime import date, timedelta

import pytest

from src.algorithms.performance import (
    CTL_DAYS,
    ATL_DAYS,
    PMCDay,
    calculate_pmc,
    compute_trend,
)


# ---------------------------------------------------------------------------
# calculate_pmc — basic mechanics
# ---------------------------------------------------------------------------

def test_empty_loads_all_zeros():
    """No loads → CTL, ATL, TSB all stay at 0."""
    start = date(2024, 1, 1)
    end = date(2024, 1, 7)
    result = calculate_pmc({}, start, end)

    assert len(result) == 7
    for day in result:
        assert day.ctl == 0.0
        assert day.atl == 0.0
        assert day.tsb == 0.0
        assert day.daily_load == 0.0


def test_series_length():
    """Output length matches the inclusive date range."""
    start = date(2024, 3, 1)
    end = date(2024, 3, 31)
    result = calculate_pmc({}, start, end)
    assert len(result) == 31


def test_single_load_day_ctl():
    """A single 42-unit load on day 1 gives CTL = 42/42 = 1.0."""
    d = date(2024, 1, 1)
    result = calculate_pmc({d: 42.0}, d, d)
    assert len(result) == 1
    assert pytest.approx(result[0].ctl, rel=1e-6) == 42.0 / CTL_DAYS


def test_single_load_day_atl():
    """A single 7-unit load on day 1 gives ATL = 7/7 = 1.0."""
    d = date(2024, 1, 1)
    result = calculate_pmc({d: 7.0}, d, d)
    assert len(result) == 1
    assert pytest.approx(result[0].atl, rel=1e-6) == 7.0 / ATL_DAYS


def test_tsb_uses_previous_ctl_atl():
    """TSB on day 2 equals CTL - ATL at end of day 1."""
    start = date(2024, 1, 1)
    end = date(2024, 1, 2)
    loads = {start: 100.0}
    result = calculate_pmc(loads, start, end)

    # Day 1: TSB = 0 - 0 = 0 (initial state before any load applied)
    assert result[0].tsb == 0.0

    # Day 2: TSB = CTL[day1] - ATL[day1]
    expected_tsb = result[0].ctl - result[0].atl
    assert pytest.approx(result[1].tsb, rel=1e-9) == expected_tsb


def test_ctl_monotonically_increases_with_constant_load():
    """Constant daily load drives CTL upward toward that load asymptotically."""
    start = date(2024, 1, 1)
    end = date(2024, 3, 1)
    daily = {start + timedelta(days=i): 100.0 for i in range((end - start).days + 1)}
    result = calculate_pmc(daily, start, end)

    # CTL should increase monotonically
    ctl_values = [day.ctl for day in result]
    assert ctl_values == sorted(ctl_values)
    # and never exceed the load itself
    assert all(day.ctl <= 100.0 for day in result)


def test_atl_rises_faster_than_ctl():
    """ATL (7-day constant) rises faster than CTL (42-day constant) under load."""
    start = date(2024, 1, 1)
    end = date(2024, 1, 14)
    daily = {start + timedelta(days=i): 100.0 for i in range(14)}
    result = calculate_pmc(daily, start, end)

    # After day 1, ATL should always be ahead of CTL
    for day in result[1:]:
        assert day.atl > day.ctl


def test_initial_ctl_atl_seed():
    """Non-zero seed values are propagated correctly."""
    d = date(2024, 6, 1)
    result = calculate_pmc({}, d, d, initial_ctl=50.0, initial_atl=60.0)
    # With zero load, EWMA decays slightly from the initial values
    assert result[0].ctl < 50.0
    assert result[0].atl < 60.0
    # TSB = initial_ctl - initial_atl (before today's load = 0 is applied)
    assert pytest.approx(result[0].tsb, rel=1e-9) == 50.0 - 60.0


def test_missing_dates_treated_as_zero():
    """Dates not in the loads dict are treated as rest days (load = 0)."""
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    # Only day 2 has load
    result = calculate_pmc({date(2024, 1, 2): 100.0}, start, end)
    assert result[0].daily_load == 0.0
    assert result[1].daily_load == 100.0
    assert result[2].daily_load == 0.0


# ---------------------------------------------------------------------------
# compute_trend
# ---------------------------------------------------------------------------

def test_trend_improving():
    """Rising CTL over the window returns 'improving'."""
    # Build a series where CTL clearly increases
    start = date(2024, 1, 1)
    end = date(2024, 1, 14)
    daily = {start + timedelta(days=i): 100.0 for i in range(14)}
    series = calculate_pmc(daily, start, end)
    assert compute_trend(series) == "improving"


def test_trend_declining():
    """Falling CTL (load drops to zero after high training) returns 'declining'."""
    start = date(2024, 1, 1)
    end = date(2024, 3, 1)
    # High load for first half, then nothing
    midpoint = date(2024, 2, 1)
    daily = {start + timedelta(days=i): 100.0 for i in range((midpoint - start).days)}
    series = calculate_pmc(daily, start, end, initial_ctl=50.0, initial_atl=50.0)
    # Only look at the tail where CTL is falling
    tail = series[-(end - midpoint).days:]
    assert compute_trend(tail) == "declining"


def test_trend_stable_no_change():
    """Flat (no load, no seed) returns 'stable'."""
    start = date(2024, 1, 1)
    end = date(2024, 1, 10)
    series = calculate_pmc({}, start, end)
    assert compute_trend(series) == "stable"


def test_trend_single_day():
    """A single-day series cannot determine trend — returns 'stable'."""
    d = date(2024, 1, 1)
    series = calculate_pmc({d: 100.0}, d, d)
    assert compute_trend(series) == "stable"


def test_trend_empty():
    """Empty series returns 'stable'."""
    assert compute_trend([]) == "stable"
