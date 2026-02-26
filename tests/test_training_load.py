"""Tests for src/algorithms/training_load.py."""

import math
import pytest

from src.algorithms.training_load import (
    ActivityMetrics,
    calculate_training_load,
    _trimp_score,
    _power_score,
    _duration_intensity_score,
    _elevation_factor,
    _sport_factor,
    _speed_intensity_factor,
    DEFAULT_MAX_HR,
    DEFAULT_RESTING_HR,
    SPORT_FACTORS,
)


# ---------------------------------------------------------------------------
# ActivityMetrics dataclass
# ---------------------------------------------------------------------------

def test_activity_metrics_defaults():
    m = ActivityMetrics(moving_time=1800)
    assert m.sport_type == "Run"
    assert m.average_heartrate is None
    assert m.average_watts is None
    assert m.distance == 0.0


# ---------------------------------------------------------------------------
# calculate_training_load – method dispatch
# ---------------------------------------------------------------------------

def test_uses_trimp_when_hr_available():
    m = ActivityMetrics(moving_time=3600, average_heartrate=155.0)
    score = calculate_training_load(m)
    expected = _trimp_score(m)
    assert score == pytest.approx(expected)


def test_uses_power_when_no_hr_but_watts_available():
    m = ActivityMetrics(moving_time=3600, average_watts=200.0, sport_type="Ride")
    score = calculate_training_load(m)
    expected = _power_score(m)
    assert score == pytest.approx(expected)


def test_uses_dis_when_no_hr_and_no_watts():
    m = ActivityMetrics(moving_time=3600, distance=10000.0, sport_type="Run")
    score = calculate_training_load(m)
    expected = _duration_intensity_score(m)
    assert score == pytest.approx(expected)


# ---------------------------------------------------------------------------
# TRIMP score
# ---------------------------------------------------------------------------

def test_trimp_increases_with_higher_hr():
    base = ActivityMetrics(moving_time=3600, average_heartrate=140.0)
    high = ActivityMetrics(moving_time=3600, average_heartrate=170.0)
    assert _trimp_score(high) > _trimp_score(base)


def test_trimp_increases_with_longer_duration():
    short = ActivityMetrics(moving_time=1800, average_heartrate=155.0)
    long_ = ActivityMetrics(moving_time=5400, average_heartrate=155.0)
    assert _trimp_score(long_) > _trimp_score(short)


def test_trimp_uses_default_hr_constants_when_none():
    m = ActivityMetrics(moving_time=3600, average_heartrate=150.0)
    score = _trimp_score(m)
    # Verify manually with known formula
    duration_min = 60.0
    hr_ratio = (150.0 - DEFAULT_RESTING_HR) / (DEFAULT_MAX_HR - DEFAULT_RESTING_HR)
    expected_raw = duration_min * hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)
    # elevation factor = 1.0 (no elevation data), sport factor = 1.0 (Run)
    assert score == pytest.approx(expected_raw, rel=1e-3)


def test_trimp_hr_below_resting_clamps_to_zero():
    """HR below resting should not produce a negative score."""
    m = ActivityMetrics(
        moving_time=1800,
        average_heartrate=40.0,   # below DEFAULT_RESTING_HR=60
        resting_heart_rate=60,
        max_heartrate=190,
    )
    score = _trimp_score(m)
    assert score >= 0


def test_trimp_degenerate_hr_reserve():
    """max_hr == resting_hr → fallback to duration_min."""
    m = ActivityMetrics(
        moving_time=1200,
        average_heartrate=60.0,
        resting_heart_rate=60,
        max_heartrate=60,
    )
    score = _trimp_score(m)
    assert score == pytest.approx(20.0)   # 1200 / 60 = 20 minutes


# ---------------------------------------------------------------------------
# Power score
# ---------------------------------------------------------------------------

def test_power_score_increases_with_watts():
    low = ActivityMetrics(moving_time=3600, average_watts=150.0, sport_type="Ride")
    high = ActivityMetrics(moving_time=3600, average_watts=250.0, sport_type="Ride")
    assert _power_score(high) > _power_score(low)


def test_power_score_increases_with_duration():
    short = ActivityMetrics(moving_time=1800, average_watts=200.0, sport_type="Ride")
    long_ = ActivityMetrics(moving_time=5400, average_watts=200.0, sport_type="Ride")
    assert _power_score(long_) > _power_score(short)


def test_power_score_intensity_capped():
    """Very high watts should not blow up the score."""
    m = ActivityMetrics(moving_time=3600, average_watts=10000.0, sport_type="Ride")
    score = _power_score(m)
    # intensity_factor capped at 2.0 → max score = 1h × 4 × 100 = 400
    assert score <= 400.0


# ---------------------------------------------------------------------------
# Duration × Intensity fallback
# ---------------------------------------------------------------------------

def test_dis_score_positive_for_valid_activity():
    m = ActivityMetrics(moving_time=3600, distance=10000.0, sport_type="Run")
    score = _duration_intensity_score(m)
    assert score > 0


def test_dis_score_higher_for_longer_activity():
    short = ActivityMetrics(moving_time=1800, distance=5000.0, sport_type="Run")
    long_ = ActivityMetrics(moving_time=5400, distance=15000.0, sport_type="Run")
    assert _duration_intensity_score(long_) > _duration_intensity_score(short)


# ---------------------------------------------------------------------------
# Elevation factor
# ---------------------------------------------------------------------------

def test_elevation_factor_flat_is_one():
    m = ActivityMetrics(moving_time=3600, distance=10000.0, total_elevation_gain=0.0)
    assert _elevation_factor(m) == pytest.approx(1.0)


def test_elevation_factor_hilly_greater_than_one():
    m = ActivityMetrics(moving_time=3600, distance=10000.0, total_elevation_gain=500.0)
    assert _elevation_factor(m) > 1.0


def test_elevation_factor_capped_at_twenty_percent():
    m = ActivityMetrics(moving_time=3600, distance=1000.0, total_elevation_gain=100000.0)
    assert _elevation_factor(m) <= 1.20 + 1e-9


def test_elevation_factor_none_returns_one():
    m = ActivityMetrics(moving_time=3600, distance=10000.0, total_elevation_gain=None)
    assert _elevation_factor(m) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Sport factor
# ---------------------------------------------------------------------------

def test_sport_factor_known_sports():
    assert _sport_factor("Run") == pytest.approx(1.0)
    assert _sport_factor("Ride") == pytest.approx(0.75)
    assert _sport_factor("Swim") == pytest.approx(0.90)


def test_sport_factor_unknown_sport_returns_default():
    from src.algorithms.training_load import DEFAULT_SPORT_FACTOR
    assert _sport_factor("Skateboarding") == pytest.approx(DEFAULT_SPORT_FACTOR)


# ---------------------------------------------------------------------------
# Speed intensity factor
# ---------------------------------------------------------------------------

def test_speed_factor_clamped_between_half_and_1_5():
    slow = ActivityMetrics(moving_time=7200, distance=100.0, sport_type="Run")
    fast = ActivityMetrics(moving_time=60, distance=10000.0, sport_type="Run")
    assert _speed_intensity_factor(slow) == pytest.approx(0.5)
    assert _speed_intensity_factor(fast) == pytest.approx(1.5)


def test_speed_factor_zero_moving_time_returns_one():
    m = ActivityMetrics(moving_time=0, distance=10000.0, sport_type="Run")
    assert _speed_intensity_factor(m) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Integration – realistic scenarios
# ---------------------------------------------------------------------------

def test_easy_run_load_lower_than_hard_run():
    easy = ActivityMetrics(
        moving_time=3600,
        sport_type="Run",
        average_heartrate=135.0,
        max_heartrate=185,
        resting_heart_rate=55,
        distance=12000.0,
        total_elevation_gain=50.0,
    )
    hard = ActivityMetrics(
        moving_time=3600,
        sport_type="Run",
        average_heartrate=170.0,
        max_heartrate=185,
        resting_heart_rate=55,
        distance=15000.0,
        total_elevation_gain=50.0,
    )
    assert calculate_training_load(easy) < calculate_training_load(hard)


def test_run_load_higher_than_equivalent_walk():
    run = ActivityMetrics(
        moving_time=3600,
        sport_type="Run",
        distance=10000.0,
    )
    walk = ActivityMetrics(
        moving_time=3600,
        sport_type="Walk",
        distance=5000.0,
    )
    assert calculate_training_load(run) > calculate_training_load(walk)


def test_hilly_run_load_higher_than_flat_run():
    flat = ActivityMetrics(
        moving_time=3600,
        sport_type="Run",
        average_heartrate=155.0,
        distance=10000.0,
        total_elevation_gain=0.0,
    )
    hilly = ActivityMetrics(
        moving_time=3600,
        sport_type="Run",
        average_heartrate=155.0,
        distance=10000.0,
        total_elevation_gain=400.0,
    )
    assert calculate_training_load(hilly) > calculate_training_load(flat)
