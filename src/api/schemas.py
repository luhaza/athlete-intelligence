"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, computed_field


class AthleteResponse(BaseModel):
    """Athlete profile response."""
    id: int
    strava_athlete_id: int
    username: Optional[str] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    resting_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    
    @computed_field
    @property
    def full_name(self) -> str:
        """Full name of athlete."""
        if self.firstname and self.lastname:
            return f"{self.firstname} {self.lastname}"
        return self.username or "Unknown"
    
    class Config:
        from_attributes = True


class ActivitySummary(BaseModel):
    """Activity summary for list views."""
    id: int
    strava_activity_id: int
    name: str
    sport_type: str
    start_date: datetime
    start_date_local: datetime
    
    # Distances and times
    distance: float  # meters
    moving_time: int  # seconds
    elapsed_time: int  # seconds
    
    # Performance metrics
    average_speed: Optional[float] = None  # m/s
    average_heartrate: Optional[float] = None
    average_cadence: Optional[float] = None
    average_watts: Optional[float] = None
    
    # Elevation
    total_elevation_gain: Optional[float] = None
    
    # Computed fields
    @computed_field
    @property
    def distance_miles(self) -> float:
        """Distance in miles."""
        return self.distance * 0.000621371
    
    @computed_field
    @property
    def distance_km(self) -> float:
        """Distance in kilometers."""
        return self.distance / 1000
    
    @computed_field
    @property
    def duration_formatted(self) -> str:
        """Duration in HH:MM:SS format."""
        hours = self.moving_time // 3600
        minutes = (self.moving_time % 3600) // 60
        seconds = self.moving_time % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    @computed_field
    @property
    def pace_per_mile(self) -> Optional[str]:
        """Pace in min:sec per mile (for running)."""
        if self.average_speed and self.sport_type in ['Run', 'Walk', 'Hike']:
            pace_min_per_mile = 1609.34 / self.average_speed / 60
            pace_min = int(pace_min_per_mile)
            pace_sec = int((pace_min_per_mile - pace_min) * 60)
            return f"{pace_min}:{pace_sec:02d}"
        return None
    
    @computed_field
    @property
    def speed_mph(self) -> Optional[float]:
        """Speed in mph (for cycling, etc.)."""
        if self.average_speed and self.sport_type not in ['Run', 'Walk', 'Hike']:
            return self.average_speed * 2.23694
        return None
    
    class Config:
        from_attributes = True


class ActivityDetail(ActivitySummary):
    """Detailed activity response with all fields."""
    description: Optional[str] = None
    workout_type: Optional[int] = None
    timezone: Optional[str] = None
    
    # Extended metrics
    max_speed: Optional[float] = None
    max_heartrate: Optional[float] = None
    max_watts: Optional[int] = None
    weighted_average_watts: Optional[int] = None
    
    # Elevation details
    elev_high: Optional[float] = None
    elev_low: Optional[float] = None
    
    # Energy and effort
    calories: Optional[float] = None
    suffer_score: Optional[int] = None
    
    # Gear and flags
    gear_id: Optional[str] = None
    trainer: bool = False
    commute: bool = False
    manual: bool = False
    private: bool = False
    
    # Derived metrics
    training_load: Optional[float] = None
    
    @computed_field
    @property
    def elevation_gain_feet(self) -> Optional[float]:
        """Elevation gain in feet."""
        if self.total_elevation_gain:
            return self.total_elevation_gain * 3.28084
        return None


class ActivityListResponse(BaseModel):
    """Paginated list of activities."""
    total: int
    limit: int
    offset: int
    activities: List[ActivitySummary]


class StreamData(BaseModel):
    """Stream data for a single stream type."""
    data: List[Any]
    length: int
    resolution: Optional[str] = None
    series_type: Optional[str] = None


class ActivityStreamsResponse(BaseModel):
    """Activity streams response."""
    activity_id: int
    streams: Dict[str, StreamData]


class LapSummary(BaseModel):
    """Lap summary data."""
    lap_index: int
    name: Optional[str] = None
    distance: float  # meters
    moving_time: int  # seconds
    elapsed_time: int  # seconds
    average_speed: Optional[float] = None
    average_heartrate: Optional[float] = None
    average_cadence: Optional[float] = None
    average_watts: Optional[float] = None
    
    @computed_field
    @property
    def distance_miles(self) -> float:
        """Distance in miles."""
        return self.distance * 0.000621371
    
    @computed_field
    @property
    def pace_per_mile(self) -> Optional[str]:
        """Pace in min:sec per mile."""
        if self.average_speed:
            pace_min_per_mile = 1609.34 / self.average_speed / 60
            pace_min = int(pace_min_per_mile)
            pace_sec = int((pace_min_per_mile - pace_min) * 60)
            return f"{pace_min}:{pace_sec:02d}"
        return None
    
    class Config:
        from_attributes = True


class AthleteStatsResponse(BaseModel):
    """Aggregate statistics for an athlete."""
    athlete_id: int
    full_name: str
    total_activities: int
    total_distance_miles: float
    total_distance_km: float
    total_moving_time_hours: float
    total_elevation_gain_feet: float
    activities_by_sport: Dict[str, int]


class AdvancedTrainingLoadResponse(BaseModel):
    """Detailed training load breakdown for an activity."""
    activity_id: int
    activity_name: str
    sport_type: str
    start_date: datetime
    
    # Legacy metric
    legacy_trimp: Optional[float] = Field(None, description="Aggregate-based TRIMP score")
    
    # Advanced metrics
    advanced_load: float = Field(description="Total advanced training load score")
    base_trimp: float = Field(description="Instantaneous TRIMP from HR stream")
    zone_weighted_load: float = Field(description="Time-in-zones weighted score")
    variability_factor: float = Field(description="HR variability multiplier (1.0-1.5)")
    anaerobic_load: float = Field(description="Extra load from time above threshold")
    elevation_stress: float = Field(description="Load contribution from climbing")
    efficiency_penalty: float = Field(description="Fatigue/decoupling penalty")
    
    # Zone distribution
    time_in_zones: Dict[int, int] = Field(description="Seconds in each HR zone (1-5)")
    zone_percentages: Dict[int, float] = Field(description="Percentage in each zone")
    
    class Config:
        from_attributes = True


class AthleteUpdateRequest(BaseModel):
    """Request body for PATCH /athlete."""
    max_heart_rate: Optional[int] = Field(None, ge=100, le=250, description="Max heart rate in bpm")
    resting_heart_rate: Optional[int] = Field(None, ge=30, le=100, description="Resting heart rate in bpm")


class PerformanceDaySnapshot(BaseModel):
    """PMC metrics for a single day."""
    date: str           # ISO date string YYYY-MM-DD
    daily_load: float
    ctl: float          # Chronic Training Load (fitness)
    atl: float          # Acute Training Load (fatigue)
    tsb: float          # Training Stress Balance (form)


class PerformanceResponse(BaseModel):
    """Response for GET /athlete/performance."""
    start_date: str
    end_date: str
    series: List[PerformanceDaySnapshot]
    current_ctl: float
    current_atl: float
    current_tsb: float
    trend: str          # 'improving', 'declining', or 'stable'


class LoadPeriodSummary(BaseModel):
    """Load summary for a single week or month."""
    period_label: str           # e.g. "2024-W22" or "2024-06"
    start_date: str             # ISO date YYYY-MM-DD
    end_date: str               # ISO date YYYY-MM-DD
    total_load: float
    total_distance_km: float
    total_moving_time_hours: float
    total_activities: int
    activities_by_sport: Dict[str, int]


class LoadSummaryResponse(BaseModel):
    """Response for GET /athlete/load/summary."""
    period: str                         # 'weekly' or 'monthly'
    periods: List[LoadPeriodSummary]


class TrainingLoadComparison(BaseModel):
    """Comparison between legacy and advanced training load methods."""
    activity_id: int
    activity_name: str
    
    # Scores
    legacy_trimp: float = Field(description="Aggregate-based TRIMP")
    advanced_load: float = Field(description="Stream-based advanced load")
    difference: float = Field(description="Advanced - Legacy")
    percent_difference: float = Field(description="Percentage difference")
    
    # Interpretation
    interpretation: str = Field(description="What the difference means")
    has_intervals: bool = Field(description="Detected interval workout")
    has_elevation: bool = Field(description="Significant climbing detected")
    has_anaerobic_efforts: bool = Field(description="Time spent above threshold")
    
    class Config:
        from_attributes = True
