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
