"""Training zone definitions and athlete-specific thresholds.

This module provides centralized configuration for training zones and
physiological thresholds. Currently configured for single-user MVP with
global defaults, but designed to support per-athlete customization in
Phase 8 (multi-user).

Usage
-----
    from src.config.training_zones import get_hr_zones, get_athlete_thresholds
    
    # Get HR zones (returns global default for now)
    zones = get_hr_zones(athlete_id=1)
    
    # Get athlete HR thresholds
    thresholds = get_athlete_thresholds(athlete_id=1)

Future Multi-User Support
--------------------------
When Phase 8 is implemented, zones can be customized per athlete:
    1. Store custom zones in Athlete.zone_config JSON field
    2. get_hr_zones() will check database for custom zones first
    3. Fall back to DEFAULT_HR_ZONES if none defined
"""

from typing import Dict, Tuple, Optional


# ---------------------------------------------------------------------------
# Heart Rate Zone Configuration
# ---------------------------------------------------------------------------
# Format: zone_number: (lower_percent, upper_percent, stress_weight)
# Percentages are relative to max heart rate (0.0 - 1.0)
# Stress weight determines how fatiguing time in this zone is

DEFAULT_HR_ZONES: Dict[int, Tuple[float, float, float]] = {
    1: (0.50, 0.60, 1.0),   # Recovery: 50-60% max HR, minimal stress
    2: (0.60, 0.70, 1.2),   # Easy: 60-70% max HR, aerobic base building
    3: (0.70, 0.80, 1.5),   # Tempo: 70-80% max HR, moderate stress
    4: (0.80, 0.90, 2.2),   # Threshold: 80-90% max HR, high stress, lactate production
    5: (0.90, 1.00, 3.5),   # VO2max: 90-100% max HR, severe stress, significant recovery needed
}

# Zone names for display purposes
ZONE_NAMES = {
    1: "Recovery",
    2: "Easy Aerobic",
    3: "Tempo",
    4: "Lactate Threshold",
    5: "VO2max",
}


# ---------------------------------------------------------------------------
# Default Physiological Thresholds
# ---------------------------------------------------------------------------
# These are reasonable defaults for an average adult athlete.
# In Phase 8, these will be pulled from Athlete model per user.

DEFAULT_MAX_HR = 190          # bpm - Maximum heart rate
DEFAULT_RESTING_HR = 60       # bpm - Resting heart rate
DEFAULT_THRESHOLD_HR_PERCENT = 0.88  # Lactate threshold as % of max HR (typically 85-92%)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_hr_zones(athlete_id: Optional[int] = None) -> Dict[int, Tuple[float, float, float]]:
    """Get heart rate zones for an athlete.
    
    Currently returns global default zones for single-user MVP.
    
    Future (Phase 8): Will check Athlete.zone_config in database for
    custom zones and fall back to defaults if none defined.
    
    Parameters
    ----------
    athlete_id : int, optional
        Athlete ID. Currently unused (single-user MVP).
        Will be used in Phase 8 to load per-athlete zones.
    
    Returns
    -------
    dict
        Zone definitions: {zone_number: (lower_%, upper_%, weight)}
    
    Examples
    --------
    >>> zones = get_hr_zones()
    >>> zones[4]  # Threshold zone
    (0.80, 0.90, 2.2)
    """
    # TODO Phase 8: Query database for athlete-specific zones
    # if athlete_id:
    #     athlete = session.query(Athlete).get(athlete_id)
    #     if athlete and athlete.zone_config:
    #         return athlete.zone_config
    
    return DEFAULT_HR_ZONES


def get_zone_name(zone_number: int) -> str:
    """Get display name for a zone number.
    
    Parameters
    ----------
    zone_number : int
        Zone number (1-5).
    
    Returns
    -------
    str
        Human-readable zone name.
    """
    return ZONE_NAMES.get(zone_number, f"Zone {zone_number}")


class AthleteThresholds:
    """Container for athlete-specific HR thresholds.
    
    Attributes
    ----------
    max_hr : int
        Maximum heart rate in bpm.
    resting_hr : int
        Resting heart rate in bpm.
    threshold_hr : int
        Lactate threshold HR in bpm.
    threshold_hr_percent : float
        Lactate threshold as percent of max HR.
    """
    
    def __init__(
        self,
        max_hr: int,
        resting_hr: int,
        threshold_hr: Optional[int] = None,
        threshold_hr_percent: Optional[float] = None,
    ):
        self.max_hr = max_hr
        self.resting_hr = resting_hr
        
        # Calculate threshold HR if not provided
        if threshold_hr:
            self.threshold_hr = threshold_hr
            self.threshold_hr_percent = threshold_hr / max_hr
        elif threshold_hr_percent:
            self.threshold_hr_percent = threshold_hr_percent
            self.threshold_hr = int(max_hr * threshold_hr_percent)
        else:
            self.threshold_hr_percent = DEFAULT_THRESHOLD_HR_PERCENT
            self.threshold_hr = int(max_hr * DEFAULT_THRESHOLD_HR_PERCENT)


def get_athlete_thresholds(
    athlete_id: Optional[int] = None,
    max_hr: Optional[int] = None,
    resting_hr: Optional[int] = None,
) -> AthleteThresholds:
    """Get heart rate thresholds for an athlete.
    
    For single-user MVP, uses provided values or global defaults.
    
    Future (Phase 8): Will query Athlete model from database to get
    stored max_heart_rate, resting_heart_rate, and threshold_heart_rate.
    
    Parameters
    ----------
    athlete_id : int, optional
        Athlete ID. Currently unused (single-user MVP).
        Will be used in Phase 8 to load from database.
    max_hr : int, optional
        Override max heart rate. If None, uses DEFAULT_MAX_HR.
    resting_hr : int, optional
        Override resting heart rate. If None, uses DEFAULT_RESTING_HR.
    
    Returns
    -------
    AthleteThresholds
        Container with max_hr, resting_hr, threshold_hr fields.
    
    Examples
    --------
    >>> thresholds = get_athlete_thresholds(max_hr=185, resting_hr=55)
    >>> thresholds.max_hr
    185
    >>> thresholds.threshold_hr
    162  # 88% of 185
    """
    # TODO Phase 8: Query database for athlete-specific thresholds
    # if athlete_id:
    #     athlete = session.query(Athlete).get(athlete_id)
    #     if athlete:
    #         max_hr = athlete.max_heart_rate or DEFAULT_MAX_HR
    #         resting_hr = athlete.resting_heart_rate or DEFAULT_RESTING_HR
    
    return AthleteThresholds(
        max_hr=max_hr or DEFAULT_MAX_HR,
        resting_hr=resting_hr or DEFAULT_RESTING_HR,
    )


# ---------------------------------------------------------------------------
# Zone Customization Helpers (for future use)
# ---------------------------------------------------------------------------

def validate_hr_zones(zones: Dict[int, Tuple[float, float, float]]) -> bool:
    """Validate that HR zones are properly configured.
    
    Checks:
    - All zone numbers 1-5 present
    - Percentages are in valid range (0.0-1.0)
    - Zones don't overlap
    - Zones are in ascending order
    - Weights are positive
    
    Parameters
    ----------
    zones : dict
        Zone configuration to validate.
    
    Returns
    -------
    bool
        True if valid, raises ValueError if invalid.
    
    Raises
    ------
    ValueError
        If zones are invalid with description of problem.
    """
    if set(zones.keys()) != {1, 2, 3, 4, 5}:
        raise ValueError("Must have exactly 5 zones numbered 1-5")
    
    for zone_num in sorted(zones.keys()):
        lower, upper, weight = zones[zone_num]
        
        # Check percentages in valid range
        if not (0.0 <= lower <= 1.0 and 0.0 <= upper <= 1.0):
            raise ValueError(f"Zone {zone_num} percentages must be between 0.0 and 1.0")
        
        # Check lower < upper
        if lower >= upper:
            raise ValueError(f"Zone {zone_num} lower bound must be less than upper bound")
        
        # Check weight is positive
        if weight <= 0:
            raise ValueError(f"Zone {zone_num} weight must be positive")
        
        # Check zones don't overlap with next zone
        if zone_num < 5:
            next_lower = zones[zone_num + 1][0]
            if upper > next_lower:
                raise ValueError(f"Zone {zone_num} overlaps with Zone {zone_num + 1}")
    
    return True


def create_custom_zones(
    z1_upper: float = 0.60,
    z2_upper: float = 0.70,
    z3_upper: float = 0.80,
    z4_upper: float = 0.90,
    z1_weight: float = 1.0,
    z2_weight: float = 1.2,
    z3_weight: float = 1.5,
    z4_weight: float = 2.2,
    z5_weight: float = 3.5,
) -> Dict[int, Tuple[float, float, float]]:
    """Create custom HR zones with specified boundaries and weights.
    
    Convenience function for generating zone configs. Validates zones
    before returning.
    
    Parameters
    ----------
    z1_upper : float
        Upper bound for Zone 1 (as % of max HR).
    z2_upper : float
        Upper bound for Zone 2.
    z3_upper : float
        Upper bound for Zone 3.
    z4_upper : float
        Upper bound for Zone 4.
    z1_weight - z5_weight : float
        Stress weights for each zone.
    
    Returns
    -------
    dict
        Validated zone configuration.
    
    Examples
    --------
    # Create zones based on 5-zone model from Joe Friel
    >>> friel_zones = create_custom_zones(
    ...     z1_upper=0.62,  # 62% max HR
    ...     z2_upper=0.75,  # 75% max HR
    ...     z3_upper=0.85,  # 85% max HR
    ...     z4_upper=0.92,  # 92% max HR
    ... )
    """
    zones = {
        1: (0.50, z1_upper, z1_weight),
        2: (z1_upper, z2_upper, z2_weight),
        3: (z2_upper, z3_upper, z3_weight),
        4: (z3_upper, z4_upper, z4_weight),
        5: (z4_upper, 1.00, z5_weight),
    }
    
    validate_hr_zones(zones)
    return zones
