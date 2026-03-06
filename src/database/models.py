"""SQLAlchemy database models for storing Strava activities.

The schema captures all metrics needed for training-load analysis
and athlete insight generation.

Usage
-----
    from src.database.models import Base, Activity, engine_from_url

    engine = engine_from_url("sqlite:///athlete_intelligence.db")
    Base.metadata.create_all(engine)
"""

import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Athlete(Base):
    """Represents a Strava athlete profile."""

    __tablename__ = "athletes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strava_athlete_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    firstname = Column(String(100), nullable=True)
    lastname = Column(String(100), nullable=True)
    # Heart-rate thresholds used for training-load calculations
    resting_heart_rate = Column(Integer, nullable=True)   # bpm
    max_heart_rate = Column(Integer, nullable=True)       # bpm
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<Athlete strava_id={self.strava_athlete_id} name={self.firstname} {self.lastname}>"


class Activity(Base):
    """Represents a single Strava activity.

    All distance/speed values are stored in SI units (metres, m/s) to
    match the Strava API response format; unit conversion should be done
    in the presentation layer.

    Columns that may be NULL
    ------------------------
    * Heart-rate metrics – not all devices record HR.
    * Power metrics – only available with a power meter.
    * Cadence – sport-type dependent.
    * suffer_score – computed by Strava; may be absent.
    * training_load – populated by the local algorithm (see
      src/algorithms/training_load.py).
    """

    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("strava_activity_id", name="uq_strava_activity_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Identity ---
    strava_activity_id = Column(Integer, nullable=False, index=True)
    strava_athlete_id = Column(Integer, nullable=False, index=True)

    # --- Metadata ---
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sport_type = Column(String(50), nullable=False)   # e.g. "Run", "Ride", "Swim"
    workout_type = Column(Integer, nullable=True)     # Strava workout type code
    start_date = Column(DateTime, nullable=False, index=True)
    start_date_local = Column(DateTime, nullable=False)
    timezone = Column(String(100), nullable=True)

    # --- Duration (seconds) ---
    elapsed_time = Column(Integer, nullable=False)   # wall-clock time incl. pauses
    moving_time = Column(Integer, nullable=False)    # active time only

    # --- Distance & elevation (metres) ---
    distance = Column(Float, nullable=False)
    total_elevation_gain = Column(Float, nullable=True)
    elev_high = Column(Float, nullable=True)
    elev_low = Column(Float, nullable=True)

    # --- Speed (m/s) ---
    average_speed = Column(Float, nullable=True)
    max_speed = Column(Float, nullable=True)

    # --- Heart rate (bpm) ---
    average_heartrate = Column(Float, nullable=True)
    max_heartrate = Column(Float, nullable=True)

    # --- Cadence (rpm / steps-per-min) ---
    average_cadence = Column(Float, nullable=True)

    # --- Power (watts, cycling only) ---
    average_watts = Column(Float, nullable=True)
    max_watts = Column(Integer, nullable=True)
    weighted_average_watts = Column(Integer, nullable=True)  # normalised power
    device_watts = Column(Boolean, nullable=True)            # True = real power meter

    # --- Energy & effort ---
    calories = Column(Float, nullable=True)
    suffer_score = Column(Integer, nullable=True)            # Strava relative effort

    # --- Gear ---
    gear_id = Column(String(50), nullable=True)

    # --- Flags ---
    trainer = Column(Boolean, default=False, nullable=False)
    commute = Column(Boolean, default=False, nullable=False)
    manual = Column(Boolean, default=False, nullable=False)
    private = Column(Boolean, default=False, nullable=False)

    # --- Derived metrics (populated by algorithms) ---
    training_load = Column(Float, nullable=True)              # Legacy aggregate-based TRIMP
    advanced_load = Column(Float, nullable=True)              # Stream-based advanced training load
    zone_distribution = Column(JSON, nullable=True)           # Time in each HR zone (dict)

    # --- Housekeeping ---
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # --- Relationships ---
    streams = relationship("ActivityStream", back_populates="activity", cascade="all, delete-orphan")
    laps = relationship("ActivityLap", back_populates="activity", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (
            f"<Activity id={self.strava_activity_id} sport={self.sport_type} "
            f"date={self.start_date_local} load={self.training_load}>"
        )


class ActivityStream(Base):
    """Time-series data streams for an activity (heart rate, pace, power, etc.).
    
    Strava provides streams as arrays of values sampled at regular intervals.
    Each stream type (heartrate, watts, cadence, etc.) is stored as a separate row.
    The 'data' column stores the array as a JSON string for simplicity.
    
    For more efficient querying, consider using PostgreSQL's ARRAY type or
    storing each data point as a separate row.
    """

    __tablename__ = "activity_streams"
    __table_args__ = (
        UniqueConstraint("strava_activity_id", "stream_type", name="uq_activity_stream"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    strava_activity_id = Column(Integer, ForeignKey("activities.strava_activity_id"), nullable=False, index=True)
    
    # Stream type: "time", "distance", "latlng", "altitude", "velocity_smooth",
    # "heartrate", "cadence", "watts", "temp", "moving", "grade_smooth"
    stream_type = Column(String(50), nullable=False)
    
    # Array of data points stored as a JSON list: [120, 125, 130, ...]
    # For heartrate this would be BPM values, for distance it would be meters, etc.
    data = Column(JSON, nullable=False)
    
    # Number of data points
    original_size = Column(Integer, nullable=True)
    
    # Resolution of the stream (e.g., "low", "medium", "high")
    resolution = Column(String(20), nullable=True)
    
    # Whether the data was returned in its original form or resampled
    series_type = Column(String(20), nullable=True)  # "distance" or "time"
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # --- Relationships ---
    activity = relationship("Activity", back_populates="streams")

    def __repr__(self) -> str:
        return f"<ActivityStream activity_id={self.strava_activity_id} type={self.stream_type}>"


class ActivityLap(Base):
    """Represents a lap within an activity (for interval workouts, splits, etc.).
    
    Laps are useful for analyzing interval training, race splits, or
    manually marked segments during an activity.
    """

    __tablename__ = "activity_laps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strava_activity_id = Column(Integer, ForeignKey("activities.strava_activity_id"), nullable=False, index=True)
    
    # Lap metadata
    lap_index = Column(Integer, nullable=False)  # 1-indexed lap number
    name = Column(String(255), nullable=True)
    
    # Timing
    elapsed_time = Column(Integer, nullable=False)  # seconds
    moving_time = Column(Integer, nullable=False)   # seconds
    start_date = Column(DateTime, nullable=False)
    start_date_local = Column(DateTime, nullable=False)
    
    # Distance & elevation
    distance = Column(Float, nullable=False)  # meters
    total_elevation_gain = Column(Float, nullable=True)
    
    # Speed
    average_speed = Column(Float, nullable=True)  # m/s
    max_speed = Column(Float, nullable=True)      # m/s
    
    # Heart rate
    average_heartrate = Column(Float, nullable=True)  # bpm
    max_heartrate = Column(Float, nullable=True)      # bpm
    
    # Cadence
    average_cadence = Column(Float, nullable=True)
    
    # Power (cycling)
    average_watts = Column(Float, nullable=True)
    
    # Lap type indicator
    # 1 = manual, 2 = auto (distance-based), 3 = session, etc.
    lap_type = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # --- Relationships ---
    activity = relationship("Activity", back_populates="laps")

    def __repr__(self) -> str:
        return f"<ActivityLap activity_id={self.strava_activity_id} lap={self.lap_index} distance={self.distance}m>"


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------

def engine_from_url(database_url: str | None = None):
    """Create and return a SQLAlchemy engine.

    Parameters
    ----------
    database_url:
        SQLAlchemy connection URL. Falls back to the ``DATABASE_URL``
        environment variable, then to a local SQLite file.
    """
    url = database_url or os.environ.get("DATABASE_URL", "sqlite:///athlete_intelligence.db")
    return create_engine(url)


