"""Athlete profile endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.api.dependencies import get_db
from src.api.schemas import AthleteResponse, AthleteStatsResponse
from src.database.models import Athlete, Activity


router = APIRouter()


@router.get("", response_model=AthleteResponse)
async def get_athlete_profile(db: Session = Depends(get_db)):
    """Get athlete profile information.
    
    For single-user MVP, returns the first (and only) athlete.
    In Phase 8, this will be filtered by authenticated user.
    """
    athlete = db.query(Athlete).first()
    
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete profile not found")
    
    return AthleteResponse.model_validate(athlete)


@router.get("/stats", response_model=AthleteStatsResponse)
async def get_athlete_stats(db: Session = Depends(get_db)):
    """Get aggregate statistics for the athlete.
    
    Returns total activities, total distance, etc.
    """
    athlete = db.query(Athlete).first()
    
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete profile not found")
    
    # Calculate aggregate stats
    stats = db.query(
        func.count(Activity.id).label('total_activities'),
        func.sum(Activity.distance).label('total_distance'),
        func.sum(Activity.moving_time).label('total_moving_time'),
        func.sum(Activity.total_elevation_gain).label('total_elevation_gain')
    ).filter(
        Activity.strava_athlete_id == athlete.strava_athlete_id
    ).first()
    
    # Count by sport type
    sport_counts = db.query(
        Activity.sport_type,
        func.count(Activity.id).label('count')
    ).filter(
        Activity.strava_athlete_id == athlete.strava_athlete_id
    ).group_by(Activity.sport_type).all()
    
    return {
        "athlete_id": athlete.strava_athlete_id,
        "full_name": " ".join(filter(None, [athlete.firstname, athlete.lastname])) or athlete.username or "Unknown",
        "total_activities": stats.total_activities or 0,
        "total_distance_miles": (stats.total_distance * 0.000621371) if stats.total_distance else 0,
        "total_distance_km": (stats.total_distance / 1000) if stats.total_distance else 0,
        "total_moving_time_hours": (stats.total_moving_time / 3600) if stats.total_moving_time else 0,
        "total_elevation_gain_feet": (stats.total_elevation_gain * 3.28084) if stats.total_elevation_gain else 0,
        "activities_by_sport": {sport: count for sport, count in sport_counts}
    }
