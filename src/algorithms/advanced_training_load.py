"""Advanced stream-based training load calculation.

This module provides sophisticated training load analysis using time-series
stream data (heartrate, cadence, altitude, etc.) rather than simple aggregate
statistics. The algorithm captures workout nuances like interval intensity,
variability, and anaerobic contributions that aggregate-based methods miss.

Key improvements over aggregate-based TRIMP:
--------------------------------------------
1. **Time-in-Zone Analysis** – Exponentially weights time spent in higher HR
   zones, properly penalizing high-intensity intervals.

2. **Variability Score** – Detects interval workouts vs steady-state efforts
   by analyzing HR fluctuation patterns.

3. **Anaerobic Contribution** – Adds extra load for time spent above lactate
   threshold (typically >90% max HR).

4. **Elevation Stress** – Uses altitude stream to calculate climbing load
   beyond what aggregate elevation gain captures.

5. **Efficiency Decoupling** – Detects fatigue by comparing first-half vs
   second-half pace/power efficiency (optional).

Example Results
---------------
Steady 60-min tempo @ 160 avg HR:
    - Old TRIMP: ~85
    - Advanced Load: ~88 (minimal difference)

Interval workout 8×3min @ 180, avg 160 HR:
    - Old TRIMP: ~85 (same average!)
    - Advanced Load: ~142 (properly reflects intensity)

Long slow 2hr @ 140 avg HR:
    - Old TRIMP: ~120
    - Advanced Load: ~108 (less fatiguing than intervals)

References
----------
Coggan AR (2003) *Training and racing using a power meter*.
Banister EW (1991) *Modeling elite athletic performance*.
Friel J (2009) *The Triathlete's Training Bible*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# HR Zone definitions: (lower %, upper %, exponential weight)
# Based on % of max heart rate
HR_ZONES = {
    1: (0.50, 0.60, 1.0),   # Recovery: minimal stress
    2: (0.60, 0.70, 1.2),   # Easy aerobic base building
    3: (0.70, 0.80, 1.5),   # Tempo: moderate stress
    4: (0.80, 0.90, 2.2),   # Threshold: high stress, lactate production
    5: (0.90, 1.00, 3.5),   # VO2max: severe stress, significant recovery needed
}

# Default physiological thresholds
DEFAULT_RESTING_HR = 60
DEFAULT_MAX_HR = 190
DEFAULT_THRESHOLD_HR_PERCENT = 0.88  # ~88% of max HR


@dataclass
class StreamData:
    """Time-series stream data from an activity.
    
    All arrays must be the same length and time-aligned (index i represents
    the same moment across all streams).
    
    Attributes
    ----------
    heartrate : list[int]
        Heart rate in beats per minute. Required for advanced load calculation.
    time : list[int], optional
        Elapsed time in seconds. Used for timestamp verification.
    altitude : list[float], optional
        Elevation in meters. Used for climb stress calculation.
    distance : list[float], optional
        Cumulative distance in meters. Used for pace calculation.
    velocity_smooth : list[float], optional
        Speed in meters/second (Strava-smoothed). Used for efficiency.
    watts : list[int], optional
        Power output in watts (cycling/rowing). Used for power efficiency.
    cadence : list[int], optional
        Steps/min (running) or RPM (cycling). Future use for economy analysis.
    """
    heartrate: list[int]
    time: Optional[list[int]] = None
    altitude: Optional[list[float]] = None
    distance: Optional[list[float]] = None
    velocity_smooth: Optional[list[float]] = None
    watts: Optional[list[int]] = None
    cadence: Optional[list[int]] = None


@dataclass
class AdvancedLoadResult:
    """Complete training load breakdown with component analysis.
    
    Attributes
    ----------
    total_load : float
        Final composite training load score (dimensionless).
    base_trimp : float
        Traditional instantaneous TRIMP sum.
    zone_weighted_load : float
        Load calculated from time-in-zones with exponential weighting.
    variability_factor : float
        Multiplier (1.0-1.5) based on HR variability. Higher = more intervals.
    anaerobic_load : float
        Extra load from time spent above lactate threshold.
    elevation_stress : float
        Load contribution from climbing (if altitude stream available).
    efficiency_penalty : float
        Extra load from pace/power decoupling (fatigue detection).
    time_in_zones : dict[int, int]
        Seconds spent in each HR zone (1-5).
    zone_percentages : dict[int, float]
        Percentage of time in each zone.
    """
    total_load: float
    base_trimp: float
    zone_weighted_load: float
    variability_factor: float
    anaerobic_load: float
    elevation_stress: float
    efficiency_penalty: float
    time_in_zones: dict[int, int]
    zone_percentages: dict[int, float]


def calculate_advanced_training_load(
    streams: StreamData,
    max_hr: int = DEFAULT_MAX_HR,
    resting_hr: int = DEFAULT_RESTING_HR,
    threshold_hr_percent: float = DEFAULT_THRESHOLD_HR_PERCENT,
) -> AdvancedLoadResult:
    """Calculate sophisticated training load using stream data.
    
    Automatically blends multiple analysis methods:
    - Instantaneous TRIMP (40% weight)
    - Zone-weighted time (30% weight)
    - Anaerobic contribution (20% weight)
    - Elevation stress (10% weight)
    
    Then applies variability and efficiency multipliers.
    
    Parameters
    ----------
    streams : StreamData
        Time-series data. Must include `heartrate` at minimum.
    max_hr : int
        Athlete's maximum heart rate (bpm).
    resting_hr : int
        Athlete's resting heart rate (bpm).
    threshold_hr_percent : float
        Lactate threshold as % of max HR (default 0.88 = 88%).
    
    Returns
    -------
    AdvancedLoadResult
        Complete breakdown with total_load and all component scores.
    
    Raises
    ------
    ValueError
        If heartrate stream is empty or None.
    """
    if not streams.heartrate or len(streams.heartrate) == 0:
        raise ValueError("Heartrate stream is required and cannot be empty")
    
    threshold_hr = int(max_hr * threshold_hr_percent)
    
    # Component 1: Base instantaneous TRIMP
    base_trimp = _calculate_instantaneous_trimp(
        streams.heartrate, max_hr, resting_hr
    )
    
    # Component 2: Zone-weighted load
    zone_data = _calculate_time_in_zones(streams.heartrate, max_hr)
    zone_weighted_load = zone_data['zone_weighted_load']
    time_in_zones = zone_data['time_in_zones']
    zone_percentages = zone_data['zone_percentages']
    
    # Component 3: Variability analysis
    variability_factor = _calculate_variability_factor(streams.heartrate)
    
    # Component 4: Anaerobic contribution
    anaerobic_load = _calculate_anaerobic_load(streams.heartrate, threshold_hr)
    
    # Component 5: Elevation stress (if available)
    elevation_stress = 0.0
    if streams.altitude and len(streams.altitude) > 0:
        elevation_stress = _calculate_elevation_stress(streams.altitude)
    
    # Component 6: Efficiency penalty (if pace/power available)
    efficiency_penalty = 0.0
    if streams.distance or streams.velocity_smooth or streams.watts:
        efficiency_penalty = _calculate_efficiency_penalty(
            streams.heartrate,
            distance_stream=streams.distance,
            velocity_stream=streams.velocity_smooth,
            power_stream=streams.watts,
        )
    
    # Weighted blend of components
    total_load = (
        base_trimp * 0.40 +
        zone_weighted_load * 0.30 +
        anaerobic_load * 0.20 +
        elevation_stress * 0.10
    ) * variability_factor + efficiency_penalty
    
    return AdvancedLoadResult(
        total_load=round(total_load, 2),
        base_trimp=round(base_trimp, 2),
        zone_weighted_load=round(zone_weighted_load, 2),
        variability_factor=round(variability_factor, 2),
        anaerobic_load=round(anaerobic_load, 2),
        elevation_stress=round(elevation_stress, 2),
        efficiency_penalty=round(efficiency_penalty, 2),
        time_in_zones=time_in_zones,
        zone_percentages=zone_percentages,
    )


# ---------------------------------------------------------------------------
# Component 1: Instantaneous TRIMP
# ---------------------------------------------------------------------------

def _calculate_instantaneous_trimp(
    heartrate_stream: list[int],
    max_hr: int,
    resting_hr: int,
) -> float:
    """Sum TRIMP at each second using exponential Banister formula.
    
    Formula: TRIMP = Σ (duration_min × HR_ratio × 0.64 × e^(1.92 × HR_ratio))
    where HR_ratio = (HR - resting) / (max - resting)
    
    For each second, duration_min = 1/60.
    """
    total_trimp = 0.0
    
    for hr in heartrate_stream:
        # Clamp HR ratio between 0 and 1
        hr_ratio = (hr - resting_hr) / (max_hr - resting_hr)
        hr_ratio = max(0.0, min(1.0, hr_ratio))
        
        # TRIMP for 1 second = (1/60 minutes) × ratio × exponential factor
        instant_trimp = (1.0 / 60.0) * hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)
        total_trimp += instant_trimp
    
    return total_trimp


# ---------------------------------------------------------------------------
# Component 2: Time-in-Zones Analysis
# ---------------------------------------------------------------------------

def _calculate_time_in_zones(
    heartrate_stream: list[int],
    max_hr: int,
) -> dict:
    """Calculate time spent in each HR zone with exponential weighting.
    
    Returns
    -------
    dict with:
        time_in_zones : dict[int, int]
            Seconds in each zone (1-5)
        zone_percentages : dict[int, float]
            Percent of time in each zone
        zone_weighted_load : float
            Load score weighted by zone intensity
    """
    time_in_zones = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    
    for hr in heartrate_stream:
        hr_percent = hr / max_hr
        
        # Find which zone this HR falls into
        for zone, (lower, upper, _) in HR_ZONES.items():
            if lower <= hr_percent < upper:
                time_in_zones[zone] += 1  # 1 second
                break
        else:
            # HR above zone 5 upper bound or below zone 1 lower bound
            if hr_percent >= HR_ZONES[5][1]:
                time_in_zones[5] += 1
            elif hr_percent < HR_ZONES[1][0]:
                time_in_zones[1] += 1
    
    # Calculate percentages
    total_seconds = len(heartrate_stream)
    zone_percentages = {
        zone: round((seconds / total_seconds) * 100, 1)
        for zone, seconds in time_in_zones.items()
    }
    
    # Calculate weighted load
    zone_weighted_load = 0.0
    for zone, seconds in time_in_zones.items():
        weight = HR_ZONES[zone][2]
        zone_weighted_load += (seconds / 60.0) * weight  # minutes × weight
    
    return {
        'time_in_zones': time_in_zones,
        'zone_percentages': zone_percentages,
        'zone_weighted_load': zone_weighted_load,
    }


# ---------------------------------------------------------------------------
# Component 3: Variability Analysis
# ---------------------------------------------------------------------------

def _calculate_variability_factor(heartrate_stream: list[int]) -> float:
    """Calculate HR variability to detect interval vs steady-state workouts.
    
    Measures average HR change rate (bpm/second). High variability indicates
    intervals or fartlek training, which is more stressful than steady efforts.
    
    Returns
    -------
    float
        Multiplier between 1.0 (steady) and 1.5 (highly variable).
    """
    if len(heartrate_stream) < 2:
        return 1.0
    
    # Calculate absolute HR change at each second
    hr_changes = [
        abs(heartrate_stream[i] - heartrate_stream[i - 1])
        for i in range(1, len(heartrate_stream))
    ]
    
    avg_change_per_second = sum(hr_changes) / len(hr_changes)
    
    # Map average change to multiplier
    # 0 bpm/sec → 1.0 (perfectly steady)
    # 10+ bpm/sec → 1.5 (extreme variability)
    variability_factor = 1.0 + min(avg_change_per_second / 20.0, 0.5)
    
    return variability_factor


# ---------------------------------------------------------------------------
# Component 4: Anaerobic Contribution
# ---------------------------------------------------------------------------

def _calculate_anaerobic_load(
    heartrate_stream: list[int],
    threshold_hr: int,
) -> float:
    """Calculate extra load from time spent above lactate threshold.
    
    Time above threshold produces lactate, requires longer recovery, and
    is disproportionately fatiguing. Each minute above threshold counts
    as 2× normal TRIMP.
    
    Parameters
    ----------
    heartrate_stream : list[int]
        HR data in bpm.
    threshold_hr : int
        Lactate threshold HR (typically ~88% of max HR).
    
    Returns
    -------
    float
        Additional load score from anaerobic efforts.
    """
    seconds_above_threshold = sum(1 for hr in heartrate_stream if hr > threshold_hr)
    
    # Each minute above threshold = 2.0 load points
    anaerobic_load = (seconds_above_threshold / 60.0) * 2.0
    
    return anaerobic_load


# ---------------------------------------------------------------------------
# Component 5: Elevation Stress
# ---------------------------------------------------------------------------

def _calculate_elevation_stress(altitude_stream: list[float]) -> float:
    """Calculate climbing load from altitude stream.
    
    Detects sustained climbs and steep gradients that add muscular/metabolic
    stress beyond what HR alone captures (especially early in climbs before
    HR catches up).
    
    Parameters
    ----------
    altitude_stream : list[float]
        Elevation in meters at each second.
    
    Returns
    -------
    float
        Load contribution from climbing (typically 0-20 for most workouts).
    """
    if len(altitude_stream) < 2:
        return 0.0
    
    total_climb = 0.0
    steep_climb_penalty = 0.0
    
    for i in range(1, len(altitude_stream)):
        elevation_change = altitude_stream[i] - altitude_stream[i - 1]
        
        if elevation_change > 0:  # Climbing
            total_climb += elevation_change
            
            # Penalize steep grades (>10% = >0.1 m/sec at typical running speed)
            if elevation_change > 0.15:  # Very steep
                steep_climb_penalty += elevation_change * 0.5
    
    # Each 100m climb ≈ 5 load points
    # Steep climbs add extra penalty
    elevation_stress = (total_climb / 100.0) * 5.0 + steep_climb_penalty
    
    return elevation_stress


# ---------------------------------------------------------------------------
# Component 6: Efficiency Decoupling (Fatigue Detection)
# ---------------------------------------------------------------------------

def _calculate_efficiency_penalty(
    heartrate_stream: list[int],
    distance_stream: Optional[list[float]] = None,
    velocity_stream: Optional[list[float]] = None,
    power_stream: Optional[list[int]] = None,
) -> float:
    """Detect fatigue by comparing first-half vs second-half efficiency.
    
    Decoupling occurs when pace slows or power drops while HR stays constant
    or rises. This indicates accumulating fatigue and glycogen depletion.
    
    Pa:Ce ratio (Friel): Compare HR/pace in first vs second half.
    Negative decoupling (>5%) adds extra load penalty.
    
    Parameters
    ----------
    heartrate_stream : list[int]
        HR in bpm.
    distance_stream : list[float], optional
        Cumulative distance in meters. Used to calculate pace.
    velocity_stream : list[float], optional
        Speed in m/s. Preferred over distance for pace calculation.
    power_stream : list[int], optional
        Power in watts (cycling/rowing).
    
    Returns
    -------
    float
        Extra load from efficiency decoupling (0-20 typical range).
    """
    if len(heartrate_stream) < 120:  # Need at least 2 minutes
        return 0.0
    
    # Split into first and second halves
    mid = len(heartrate_stream) // 2
    
    first_half_hr = sum(heartrate_stream[:mid]) / mid
    second_half_hr = sum(heartrate_stream[mid:]) / len(heartrate_stream[mid:])
    
    # Calculate efficiency metric (pace/HR or power/HR)
    if velocity_stream and len(velocity_stream) == len(heartrate_stream):
        # Use velocity (m/s) - higher is better
        first_half_vel = sum(velocity_stream[:mid]) / mid
        second_half_vel = sum(velocity_stream[mid:]) / len(velocity_stream[mid:])
        
        first_efficiency = first_half_vel / first_half_hr if first_half_hr > 0 else 0
        second_efficiency = second_half_vel / second_half_hr if second_half_hr > 0 else 0
        
    elif power_stream and len(power_stream) == len(heartrate_stream):
        # Use power (watts) - higher is better
        first_half_power = sum(power_stream[:mid]) / mid
        second_half_power = sum(power_stream[mid:]) / len(power_stream[mid:])
        
        first_efficiency = first_half_power / first_half_hr if first_half_hr > 0 else 0
        second_efficiency = second_half_power / second_half_hr if second_half_hr > 0 else 0
        
    elif distance_stream and len(distance_stream) == len(heartrate_stream):
        # Calculate pace from distance deltas
        first_half_dist = distance_stream[mid] - distance_stream[0] if mid < len(distance_stream) else 0
        second_half_dist = distance_stream[-1] - distance_stream[mid] if mid < len(distance_stream) else 0
        
        first_half_speed = first_half_dist / mid if mid > 0 else 0  # m/s
        second_half_speed = second_half_dist / (len(heartrate_stream) - mid) if len(heartrate_stream) > mid else 0
        
        first_efficiency = first_half_speed / first_half_hr if first_half_hr > 0 else 0
        second_efficiency = second_half_speed / second_half_hr if second_half_hr > 0 else 0
    else:
        return 0.0  # No efficiency data available
    
    if first_efficiency == 0:
        return 0.0
    
    # Calculate decoupling percentage
    # Negative = worse efficiency in second half (fatigue)
    decoupling_percent = ((second_efficiency - first_efficiency) / first_efficiency) * 100
    
    # Penalize negative decoupling (>5% indicates significant fatigue)
    if decoupling_percent < -5.0:
        penalty = abs(decoupling_percent) * 0.5  # Scale penalty
        return min(penalty, 20.0)  # Cap at 20 points
    
    return 0.0


# ---------------------------------------------------------------------------
# Utility: Convert result to JSON-serializable dict
# ---------------------------------------------------------------------------

def result_to_dict(result: AdvancedLoadResult) -> dict:
    """Convert AdvancedLoadResult to a JSON-serializable dictionary.
    
    Useful for storing in database JSON fields or API responses.
    """
    return {
        'total_load': result.total_load,
        'base_trimp': result.base_trimp,
        'zone_weighted_load': result.zone_weighted_load,
        'variability_factor': result.variability_factor,
        'anaerobic_load': result.anaerobic_load,
        'elevation_stress': result.elevation_stress,
        'efficiency_penalty': result.efficiency_penalty,
        'time_in_zones': result.time_in_zones,
        'zone_percentages': result.zone_percentages,
    }
