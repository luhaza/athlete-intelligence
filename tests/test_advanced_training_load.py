"""Tests for src/algorithms/advanced_training_load.py."""

import math
import pytest

from src.algorithms.advanced_training_load import (
    StreamData,
    AdvancedLoadResult,
    calculate_advanced_training_load,
    _calculate_instantaneous_trimp,
    _calculate_time_in_zones,
    _calculate_variability_factor,
    _calculate_anaerobic_load,
    _calculate_elevation_stress,
    _calculate_efficiency_penalty,
    result_to_dict,
    DEFAULT_MAX_HR,
    DEFAULT_RESTING_HR,
)


# ---------------------------------------------------------------------------
# StreamData dataclass
# ---------------------------------------------------------------------------

def test_stream_data_minimal():
    s = StreamData(heartrate=[120, 130, 140])
    assert s.heartrate == [120, 130, 140]
    assert s.altitude is None
    assert s.watts is None
    assert s.time is None


# ---------------------------------------------------------------------------
# calculate_advanced_training_load — top-level dispatch
# ---------------------------------------------------------------------------

def test_returns_advanced_load_result():
    result = calculate_advanced_training_load(StreamData(heartrate=[150] * 3600))
    assert isinstance(result, AdvancedLoadResult)
    assert result.total_load > 0


def test_empty_heartrate_raises():
    with pytest.raises(ValueError, match="Heartrate stream is required"):
        calculate_advanced_training_load(StreamData(heartrate=[]))


def test_higher_hr_higher_load():
    low = calculate_advanced_training_load(StreamData(heartrate=[130] * 3600))
    high = calculate_advanced_training_load(StreamData(heartrate=[170] * 3600))
    assert high.total_load > low.total_load


def test_longer_activity_higher_load():
    short = calculate_advanced_training_load(StreamData(heartrate=[150] * 1800))
    long_ = calculate_advanced_training_load(StreamData(heartrate=[150] * 5400))
    assert long_.total_load > short.total_load


def test_interval_workout_higher_than_steady_same_average():
    """Alternating HR (intervals) should outscore a steady effort at identical average HR."""
    steady_hr = [155] * 3600

    # Alternating 175/135 — average ≈ 155, but high variability
    interval_hr = ([175] * 30 + [135] * 30) * 60

    steady = calculate_advanced_training_load(StreamData(heartrate=steady_hr))
    intervals = calculate_advanced_training_load(StreamData(heartrate=interval_hr))
    assert intervals.total_load > steady.total_load


def test_elevation_stress_added_with_altitude_stream():
    hr = [150] * 3600
    flat = calculate_advanced_training_load(StreamData(heartrate=hr))
    # Gradual 360 m climb over the hour
    altitude = [100.0 + i * 0.1 for i in range(3600)]
    climbing = calculate_advanced_training_load(StreamData(heartrate=hr, altitude=altitude))
    assert climbing.elevation_stress > 0
    assert climbing.elevation_stress > flat.elevation_stress


def test_result_has_all_zone_keys():
    result = calculate_advanced_training_load(StreamData(heartrate=[150] * 1800))
    assert set(result.time_in_zones.keys()) == {1, 2, 3, 4, 5}
    assert set(result.zone_percentages.keys()) == {1, 2, 3, 4, 5}


# ---------------------------------------------------------------------------
# _calculate_instantaneous_trimp
# ---------------------------------------------------------------------------

def test_instantaneous_trimp_positive():
    result = _calculate_instantaneous_trimp([150] * 60, DEFAULT_MAX_HR, DEFAULT_RESTING_HR)
    assert result > 0


def test_instantaneous_trimp_increases_with_hr():
    low = _calculate_instantaneous_trimp([130] * 60, DEFAULT_MAX_HR, DEFAULT_RESTING_HR)
    high = _calculate_instantaneous_trimp([170] * 60, DEFAULT_MAX_HR, DEFAULT_RESTING_HR)
    assert high > low


def test_instantaneous_trimp_hr_below_resting_is_zero():
    result = _calculate_instantaneous_trimp([40] * 60, DEFAULT_MAX_HR, DEFAULT_RESTING_HR)
    assert result == pytest.approx(0.0)


def test_instantaneous_trimp_matches_formula():
    """Verify against the Banister formula for a single steady HR."""
    hr_val = 150
    n = 600  # 10 minutes
    result = _calculate_instantaneous_trimp([hr_val] * n, DEFAULT_MAX_HR, DEFAULT_RESTING_HR)
    hr_ratio = (hr_val - DEFAULT_RESTING_HR) / (DEFAULT_MAX_HR - DEFAULT_RESTING_HR)
    expected = (n / 60.0) * hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)
    assert result == pytest.approx(expected, rel=1e-3)


# ---------------------------------------------------------------------------
# _calculate_time_in_zones
# ---------------------------------------------------------------------------

def test_time_in_zones_all_zone1():
    max_hr = 190
    # Zone 1 is 50–60 % → 95–114 bpm
    result = _calculate_time_in_zones([100] * 300, max_hr)
    assert result['time_in_zones'][1] == 300
    assert result['time_in_zones'][5] == 0
    assert result['zone_percentages'][1] == pytest.approx(100.0)


def test_time_in_zones_all_zone5():
    max_hr = 190
    # Zone 5 is 90–100 % → 171–190 bpm
    result = _calculate_time_in_zones([185] * 300, max_hr)
    assert result['time_in_zones'][5] == 300
    assert result['zone_weighted_load'] > 0


def test_time_in_zones_percentages_sum_100():
    hr = [100, 120, 140, 160, 180] * 200
    result = _calculate_time_in_zones(hr, 190)
    total = sum(result['zone_percentages'].values())
    assert total == pytest.approx(100.0, abs=1.0)


def test_time_in_zones_returns_required_keys():
    result = _calculate_time_in_zones([150] * 60, 190)
    assert 'time_in_zones' in result
    assert 'zone_percentages' in result
    assert 'zone_weighted_load' in result


def test_time_in_zones_higher_zone_higher_weight():
    max_hr = 190
    z2 = _calculate_time_in_zones([120] * 600, max_hr)['zone_weighted_load']  # ~63 %
    z4 = _calculate_time_in_zones([162] * 600, max_hr)['zone_weighted_load']  # ~85 %
    assert z4 > z2


# ---------------------------------------------------------------------------
# _calculate_variability_factor
# ---------------------------------------------------------------------------

def test_variability_factor_steady_is_one():
    factor = _calculate_variability_factor([150] * 300)
    assert factor == pytest.approx(1.0)


def test_variability_factor_highly_variable_above_one():
    factor = _calculate_variability_factor([130, 180] * 150)
    assert factor > 1.0


def test_variability_factor_capped_at_1_5():
    factor = _calculate_variability_factor([60, 190] * 1000)
    assert factor <= 1.5


def test_variability_factor_single_point():
    assert _calculate_variability_factor([150]) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _calculate_anaerobic_load
# ---------------------------------------------------------------------------

def test_anaerobic_load_zero_below_threshold():
    threshold = int(DEFAULT_MAX_HR * 0.88)
    load = _calculate_anaerobic_load([150] * 3600, threshold)
    assert load == pytest.approx(0.0)


def test_anaerobic_load_positive_above_threshold():
    threshold = int(DEFAULT_MAX_HR * 0.88)
    load = _calculate_anaerobic_load([180] * 3600, threshold)
    assert load > 0


def test_anaerobic_load_one_minute_equals_two():
    """60 seconds above threshold should produce load of 2.0 (60/60 × 2.0)."""
    threshold = 167
    load = _calculate_anaerobic_load([175] * 60, threshold)
    assert load == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# _calculate_elevation_stress
# ---------------------------------------------------------------------------

def test_elevation_stress_flat_is_zero():
    stress = _calculate_elevation_stress([100.0] * 300)
    assert stress == pytest.approx(0.0)


def test_elevation_stress_climbing_positive():
    # 100 m climb over 100 seconds
    altitude = [100.0 + i for i in range(100)]
    stress = _calculate_elevation_stress(altitude)
    assert stress > 0


def test_elevation_stress_descending_is_zero():
    altitude = [200.0 - i for i in range(100)]
    stress = _calculate_elevation_stress(altitude)
    assert stress == pytest.approx(0.0)


def test_elevation_stress_100m_climb():
    """100 m total gain with gentle grade (≤0.15 m/s, no steep penalty) = 5.0 load points."""
    # 100 m over 1000 seconds → each step = 0.1 m (below 0.15 steep threshold)
    altitude = [i * 0.1 for i in range(1001)]
    stress = _calculate_elevation_stress(altitude)
    assert stress == pytest.approx(5.0, rel=0.01)


def test_elevation_stress_single_point():
    assert _calculate_elevation_stress([100.0]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _calculate_efficiency_penalty
# ---------------------------------------------------------------------------

def test_efficiency_penalty_no_streams_returns_zero():
    penalty = _calculate_efficiency_penalty([150] * 3600)
    assert penalty == pytest.approx(0.0)


def test_efficiency_penalty_consistent_velocity_no_penalty():
    hr = [150] * 3600
    velocity = [3.0] * 3600
    penalty = _calculate_efficiency_penalty(hr, velocity_stream=velocity)
    assert penalty == pytest.approx(0.0)


def test_efficiency_penalty_severe_decoupling_positive():
    """Speed halves in second half at same HR → significant penalty."""
    hr = [155] * 3600
    velocity = [3.0] * 1800 + [1.5] * 1800
    penalty = _calculate_efficiency_penalty(hr, velocity_stream=velocity)
    assert penalty > 0


def test_efficiency_penalty_capped_at_twenty():
    hr = [155] * 3600
    velocity = [3.0] * 1800 + [0.001] * 1800
    penalty = _calculate_efficiency_penalty(hr, velocity_stream=velocity)
    assert penalty <= 20.0


def test_efficiency_penalty_too_short_returns_zero():
    hr = [150] * 60
    velocity = [3.0] * 60
    assert _calculate_efficiency_penalty(hr, velocity_stream=velocity) == pytest.approx(0.0)


def test_efficiency_penalty_power_stream():
    hr = [155] * 3600
    power = [220] * 1800 + [110] * 1800  # power drops 50 %
    penalty = _calculate_efficiency_penalty(hr, power_stream=power)
    assert penalty > 0


# ---------------------------------------------------------------------------
# result_to_dict
# ---------------------------------------------------------------------------

def test_result_to_dict_has_all_keys():
    result = calculate_advanced_training_load(StreamData(heartrate=[150] * 3600))
    d = result_to_dict(result)
    expected_keys = {
        'total_load', 'base_trimp', 'zone_weighted_load', 'variability_factor',
        'anaerobic_load', 'elevation_stress', 'efficiency_penalty',
        'time_in_zones', 'zone_percentages',
    }
    assert set(d.keys()) == expected_keys


def test_result_to_dict_values_match_result():
    result = calculate_advanced_training_load(StreamData(heartrate=[150] * 3600))
    d = result_to_dict(result)
    assert d['total_load'] == result.total_load
    assert d['base_trimp'] == result.base_trimp
    assert d['time_in_zones'] == result.time_in_zones
    assert d['zone_percentages'] == result.zone_percentages
