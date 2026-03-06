"""Training load analysis endpoints.

Provides detailed breakdowns of training load calculations using both
aggregate-based and advanced stream-based methods.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ...database.models import Activity
from ..schemas import AdvancedTrainingLoadResponse, TrainingLoadComparison


router = APIRouter()


@router.get("/{activity_id}/training-load", response_model=AdvancedTrainingLoadResponse)
def get_activity_training_load(activity_id: int, db: Session = Depends(get_db)):
    """Get detailed training load breakdown for an activity.
    
    Returns both the advanced stream-based load calculation and the legacy
    aggregate-based TRIMP score for comparison.
    
    The advanced load provides:
    - Total load score (composite of all components)
    - Base TRIMP (instantaneous calculation from HR stream)
    - Zone-weighted load (time-in-zones analysis)
    - Variability factor (interval detection)
    - Anaerobic contribution (time above threshold)
    - Elevation stress (climbing load)
    - Efficiency penalty (fatigue/decoupling)
    - Time in each HR zone (1-5)
    - Zone percentages
    
    **Note:** Advanced load is only available for activities that have been
    synced with stream data (heartrate required).
    """
    activity = db.query(Activity).filter_by(strava_activity_id=activity_id).first()
    
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    if not activity.zone_distribution:
        raise HTTPException(
            status_code=404,
            detail="Advanced training load not available. Activity may not have stream data or has not been processed yet."
        )

    if activity.advanced_load is None:
        raise HTTPException(
            status_code=404,
            detail="Advanced training load score not yet calculated for this activity."
        )

    return AdvancedTrainingLoadResponse(
        activity_id=activity.strava_activity_id,
        activity_name=activity.name,
        sport_type=activity.sport_type,
        start_date=activity.start_date_local,
        
        # Legacy metric
        legacy_trimp=activity.training_load,
        
        # Advanced metrics
        advanced_load=activity.advanced_load,
        base_trimp=activity.zone_distribution.get('base_trimp'),
        zone_weighted_load=activity.zone_distribution.get('zone_weighted_load'),
        variability_factor=activity.zone_distribution.get('variability_factor'),
        anaerobic_load=activity.zone_distribution.get('anaerobic_load'),
        elevation_stress=activity.zone_distribution.get('elevation_stress'),
        efficiency_penalty=activity.zone_distribution.get('efficiency_penalty'),
        
        # Zone distribution
        time_in_zones=activity.zone_distribution.get('time_in_zones'),
        zone_percentages=activity.zone_distribution.get('zone_percentages'),
    )


@router.get("/{activity_id}/training-load/comparison", response_model=TrainingLoadComparison)
def compare_training_load_methods(activity_id: int, db: Session = Depends(get_db)):
    """Compare legacy vs advanced training load calculations.
    
    Shows the difference between aggregate-based TRIMP and the sophisticated
    stream-based analysis. Useful for understanding how interval workouts,
    elevation, and other factors are captured differently by each method.
    """
    activity = db.query(Activity).filter_by(strava_activity_id=activity_id).first()
    
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    if not activity.training_load or not activity.advanced_load:
        raise HTTPException(
            status_code=404,
            detail="Training load calculations not available for this activity"
        )
    
    difference = activity.advanced_load - activity.training_load
    percent_difference = (difference / activity.training_load) * 100 if activity.training_load > 0 else 0
    
    # Interpret the difference
    if abs(percent_difference) < 10:
        interpretation = "Steady-state workout with consistent effort"
    elif percent_difference > 30:
        interpretation = "High-intensity intervals or significant climbing detected"
    elif percent_difference > 10:
        interpretation = "Moderate variability or tempo segments detected"
    else:
        interpretation = "Lower intensity than average metrics suggest"
    
    return TrainingLoadComparison(
        activity_id=activity.strava_activity_id,
        activity_name=activity.name,
        legacy_trimp=activity.training_load,
        advanced_load=activity.advanced_load,
        difference=round(difference, 2),
        percent_difference=round(percent_difference, 1),
        interpretation=interpretation,
        
        # Context for interpretation
        has_intervals=(activity.zone_distribution or {}).get('variability_factor', 1.0) > 1.1,
        has_elevation=(activity.zone_distribution or {}).get('elevation_stress', 0) > 5.0,
        has_anaerobic_efforts=(activity.zone_distribution or {}).get('anaerobic_load', 0) > 5.0,
    )
