"""Training load (strain) algorithm.

This module quantifies the physiological stress imposed by a single
activity.  Three complementary methods are implemented so that a score
can always be produced regardless of which sensors were used:

1. **TRIMP** (Training Impulse) – heart-rate–based; preferred when HR
   data is available.  Based on Banister (1991) with the monotonic HR
   ratio used by Morton et al. (1990).

2. **Power-based Score** – used when reliable power data is available.
   Uses ``average_watts`` as a direct proxy for mechanical work (cycling /
   other power-meter sports).

3. **Duration × Intensity Score (DIS)** – fallback when HR and power are
   absent.  Combines moving time, distance, and elevation to estimate
   effort.

All methods return a dimensionless score on the same relative scale so
that activities can be ranked and compared.

Key metrics
-----------
* ``moving_time``           – active duration (seconds); higher ⟹ more load
* ``average_heartrate``     – mean HR during activity (bpm)
* ``max_heartrate``         – athlete's maximum HR (bpm); used to compute
                              HR intensity
* ``resting_heart_rate``    – athlete's resting HR (bpm); anchors the HR
                              reserve calculation
* ``distance``              – total distance (metres); proxy for mechanical
                              work
* ``total_elevation_gain``  – cumulative ascent (metres); increases load
                              beyond flat-equivalent effort
* ``average_watts``         – mean power output (watts); direct mechanical
                              work measure (cycling / power-based sports)
* ``sport_type``            – activity category; different sports have
                              different load profiles (see SPORT_FACTORS)

References
----------
Banister EW (1991) *Modeling elite athletic performance*.
Morton RH et al. (1990) *Modeling human performance in running*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Sport-specific intensity adjustment factors.
# These values reflect the relative cardiovascular/musculoskeletal load
# per unit of time compared to running at threshold effort.
# ---------------------------------------------------------------------------
SPORT_FACTORS: dict[str, float] = {
    "Run": 1.0,
    "TrailRun": 1.1,
    "VirtualRun": 1.0,
    "Ride": 0.75,
    "MountainBikeRide": 0.85,
    "VirtualRide": 0.70,
    "Swim": 0.90,
    "Rowing": 0.85,
    "Hike": 0.65,
    "Walk": 0.45,
    "WeightTraining": 0.60,
    "Yoga": 0.30,
}

DEFAULT_SPORT_FACTOR = 0.75

# Default physiological constants when athlete-specific values are unknown.
DEFAULT_RESTING_HR = 60   # bpm
DEFAULT_MAX_HR = 190      # bpm


@dataclass
class ActivityMetrics:
    """Container for the metrics required by the training-load algorithm.

    All fields match column names in :class:`~src.database.models.Activity`
    so that an ``Activity`` ORM object can be unpacked directly.

    Parameters
    ----------
    moving_time:
        Active duration in seconds.
    sport_type:
        Strava sport type string (e.g. ``"Run"``, ``"Ride"``).
    average_heartrate:
        Average heart rate during the activity in bpm.  ``None`` when HR
        data is unavailable.
    max_heartrate:
        Athlete's maximum heart rate in bpm.  ``None`` uses the default.
    resting_heart_rate:
        Athlete's resting heart rate in bpm.  ``None`` uses the default.
    distance:
        Total activity distance in metres.
    total_elevation_gain:
        Cumulative elevation gain in metres.  ``None`` treated as 0.
    average_watts:
        Mean power output in watts (cycling / rowing).  ``None`` when
        no power meter was used.
    """

    moving_time: int                         # seconds
    sport_type: str = "Run"
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    resting_heart_rate: Optional[float] = None
    distance: float = 0.0                    # metres
    total_elevation_gain: Optional[float] = None
    average_watts: Optional[float] = None


def calculate_training_load(metrics: ActivityMetrics) -> float:
    """Return a training-load score for the given activity metrics.

    Chooses the best available method automatically:

    * HR data present → TRIMP-based score
    * Power data present (no HR) → power-based score
    * Neither → duration × intensity fallback

    Parameters
    ----------
    metrics:
        An :class:`ActivityMetrics` instance populated with activity data.

    Returns
    -------
    float
        A non-negative training-load score.  Typical values:
        * Easy 30-min run ≈ 30–50
        * Hard 60-min run ≈ 80–120
        * Long 2-hour run ≈ 150–200
    """
    if metrics.average_heartrate is not None:
        return _trimp_score(metrics)
    if metrics.average_watts is not None:
        return _power_score(metrics)
    return _duration_intensity_score(metrics)


# ---------------------------------------------------------------------------
# Method 1 – TRIMP (heart-rate based)
# ---------------------------------------------------------------------------

def _trimp_score(metrics: ActivityMetrics) -> float:
    """Compute a TRIMP-style training-load score.

    Formula
    -------
    TRIMP = D × HRr × 0.64·e^(1.92·HRr)

    where:
    * D    = moving_time in minutes
    * HRr  = (HR_avg - HR_rest) / (HR_max - HR_rest)  [heart-rate reserve ratio]

    The exponential term reflects the disproportionate physiological cost
    of high-intensity exercise.  Sport factor scales the result so that
    equivalent-effort activities across different sports produce similar
    scores.
    """
    hr_rest = metrics.resting_heart_rate or DEFAULT_RESTING_HR
    hr_max = metrics.max_heartrate or DEFAULT_MAX_HR
    hr_avg = metrics.average_heartrate  # guaranteed non-None by caller

    duration_min = metrics.moving_time / 60.0
    hr_reserve = hr_max - hr_rest

    if hr_reserve <= 0:
        # Degenerate case: fall back to simple duration score.
        return duration_min

    hr_ratio = max(0.0, min(1.0, (hr_avg - hr_rest) / hr_reserve))

    trimp = duration_min * hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)

    # Apply elevation bonus: ~+1% per 10 m of gain per km (~1% per 1% avg
    # gradient), capped at 20%.
    trimp *= _elevation_factor(metrics)

    # Apply sport-specific scaling.
    trimp *= _sport_factor(metrics.sport_type)

    return round(trimp, 2)


# ---------------------------------------------------------------------------
# Method 2 – Power-based score (cycling / rowing)
# ---------------------------------------------------------------------------

def _power_score(metrics: ActivityMetrics) -> float:
    """Compute a power-based training-load score.

    This is a simplified TSS-like metric that does not require FTP:
    it uses average watts normalised by a reference power (3 W/kg for a
    75 kg athlete at threshold ≈ 225 W) to derive an intensity factor.

    Formula
    -------
    score = duration_hours × intensity_factor² × 100

    where intensity_factor = average_watts / REFERENCE_POWER
    """
    REFERENCE_POWER = 225.0   # watts (≈ threshold for a 75 kg athlete)
    duration_hours = metrics.moving_time / 3600.0
    intensity_factor = min(metrics.average_watts / REFERENCE_POWER, 2.0)
    score = duration_hours * (intensity_factor ** 2) * 100.0
    score *= _elevation_factor(metrics)
    score *= _sport_factor(metrics.sport_type)
    return round(score, 2)


# ---------------------------------------------------------------------------
# Method 3 – Duration × Intensity fallback
# ---------------------------------------------------------------------------

def _duration_intensity_score(metrics: ActivityMetrics) -> float:
    """Estimate training load from duration, distance, and elevation only.

    Used when neither HR nor power data are available.

    The intensity is estimated from average speed relative to an expected
    easy-effort pace for the sport type, then combined with duration.
    """
    duration_min = metrics.moving_time / 60.0
    sport_factor = _sport_factor(metrics.sport_type)

    # Speed-based intensity: compare average speed to a sport-specific
    # reference easy-effort speed.
    speed_factor = _speed_intensity_factor(metrics)

    score = duration_min * sport_factor * speed_factor
    score *= _elevation_factor(metrics)
    return round(score, 2)


# ---------------------------------------------------------------------------
# Shared helper factors
# ---------------------------------------------------------------------------

def _sport_factor(sport_type: str) -> float:
    """Return the load-scaling factor for *sport_type*."""
    return SPORT_FACTORS.get(sport_type, DEFAULT_SPORT_FACTOR)


def _elevation_factor(metrics: ActivityMetrics) -> float:
    """Return an elevation-gain bonus multiplier.

    Adds up to ~20% extra load for very hilly activities.
    Gradient proxy = elevation_gain / distance_km.
    Each percent of average gradient adds 1% load.
    """
    if not metrics.total_elevation_gain or metrics.distance <= 0:
        return 1.0
    distance_km = metrics.distance / 1000.0
    gradient_pct = (metrics.total_elevation_gain / distance_km) / 10.0
    return 1.0 + min(gradient_pct * 0.01, 0.20)


def _speed_intensity_factor(metrics: ActivityMetrics) -> float:
    """Estimate relative intensity from average speed.

    Returns a value in [0.5, 1.5] where 1.0 ≈ moderate/tempo effort.
    Reference easy-effort speeds by sport (m/s):
    """
    EASY_SPEEDS: dict[str, float] = {
        "Run": 2.5,          # ~6:40/km easy pace
        "TrailRun": 2.0,
        "VirtualRun": 2.5,
        "Ride": 7.0,         # ~25 km/h easy
        "MountainBikeRide": 5.0,
        "VirtualRide": 7.0,
        "Swim": 1.0,         # ~1:40/100 m easy
        "Rowing": 3.5,
        "Hike": 1.2,
        "Walk": 1.0,
    }
    if metrics.moving_time <= 0 or metrics.distance <= 0:
        return 1.0
    avg_speed = metrics.distance / metrics.moving_time
    ref_speed = EASY_SPEEDS.get(metrics.sport_type, 3.0)
    return max(0.5, min(avg_speed / ref_speed, 1.5))
