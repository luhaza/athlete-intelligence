"""Activity endpoints."""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import json

from src.api.dependencies import get_db
from src.api.schemas import (
    ActivityListResponse,
    ActivitySummary,
    ActivityDetail,
    ActivityStreamsResponse,
    StreamData,
    LapSummary
)
from src.database.models import Activity, ActivityStream, ActivityLap


router = APIRouter()


@router.get("", response_model=ActivityListResponse)
async def list_activities(
    limit: int = Query(20, ge=1, le=100, description="Number of activities to return"),
    offset: int = Query(0, ge=0, description="Number of activities to skip"),
    sport_type: Optional[str] = Query(None, max_length=50, description="Filter by sport type (e.g., 'Run', 'Ride')"),
    start_date: Optional[datetime] = Query(None, description="Filter activities after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter activities before this date"),
    db: Session = Depends(get_db)
):
    """Get list of activities with optional filters and pagination.
    
    Returns activities ordered by start date (most recent first).
    """
    # Validate date range
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    
    # Build query
    query = db.query(Activity)
    
    # Apply filters with parameterized queries (SQLAlchemy handles this safely)
    if sport_type:
        # Validate sport_type contains only alphanumeric and common chars
        if not sport_type.replace(' ', '').replace('_', '').replace('-', '').isalnum():
            raise HTTPException(status_code=400, detail="Invalid sport_type format")
        query = query.filter(Activity.sport_type == sport_type)
    
    if start_date:
        query = query.filter(Activity.start_date >= start_date)
    
    if end_date:
        query = query.filter(Activity.start_date <= end_date)
    
    # Get total count
    total = query.count()
    
    # Apply ordering and pagination
    activities = query.order_by(Activity.start_date.desc()).offset(offset).limit(limit).all()
    
    return ActivityListResponse(
        total=total,
        limit=limit,
        offset=offset,
        activities=[ActivitySummary.model_validate(a) for a in activities]
    )


@router.get("/{activity_id}", response_model=ActivityDetail)
async def get_activity(
    activity_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information for a single activity.
    
    Args:
        activity_id: Strava activity ID
    """
    activity = db.query(Activity).filter(
        Activity.strava_activity_id == activity_id
    ).first()
    
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    return ActivityDetail.model_validate(activity)


@router.get("/{activity_id}/streams", response_model=ActivityStreamsResponse)
async def get_activity_streams(
    activity_id: int,
    types: Optional[str] = Query(None, max_length=200, description="Comma-separated stream types to return"),
    db: Session = Depends(get_db)
):
    """Get time-series stream data for an activity.
    
    Args:
        activity_id: Strava activity ID
        types: Optional comma-separated list of stream types
               (e.g., 'heartrate,pace,altitude')
    """
    # Build streams query (no need to verify activity exists separately)
    query = db.query(ActivityStream).filter(
        ActivityStream.strava_activity_id == activity_id
    )
    
    # Filter by stream types if specified
    if types:
        stream_types = [t.strip() for t in types.split(',')]
        # Limit number of stream types to prevent abuse
        if len(stream_types) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 stream types allowed")
        # Validate each stream type
        for st in stream_types:
            if not st.replace('_', '').isalnum():
                raise HTTPException(status_code=400, detail=f"Invalid stream type: {st}")
        query = query.filter(ActivityStream.stream_type.in_(stream_types))
    
    streams = query.all()
    
    if not streams:
        raise HTTPException(status_code=404, detail="No streams found for this activity")
    
    # Convert to response format with error handling
    import logging
    logger = logging.getLogger(__name__)
    
    streams_dict = {}
    for stream in streams:
        try:
            data = json.loads(stream.data)
            streams_dict[stream.stream_type] = StreamData(
                data=data,
                length=len(data),
                resolution=stream.resolution,
                series_type=stream.series_type
            )
        except json.JSONDecodeError as e:
            # Log error but don't expose details to client
            logger.error(f"Error parsing stream {stream.stream_type} for activity {activity_id}: {str(e)}")
            continue
    
    if not streams_dict:
        raise HTTPException(status_code=500, detail="Failed to parse stream data")
    
    return ActivityStreamsResponse(
        activity_id=activity_id,
        streams=streams_dict
    )


@router.get("/{activity_id}/laps", response_model=List[LapSummary])
async def get_activity_laps(
    activity_id: int,
    db: Session = Depends(get_db)
):
    """Get lap/split data for an activity.
    
    Args:
        activity_id: Strava activity ID
    
    Returns:
        Empty list if activity has no laps or activity doesn't exist.
    """
    # Get laps ordered by lap index
    laps = db.query(ActivityLap).filter(
        ActivityLap.strava_activity_id == activity_id
    ).order_by(ActivityLap.lap_index).all()
    
    return [LapSummary.model_validate(lap) for lap in laps]
