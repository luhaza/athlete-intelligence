"""Integration tests for Strava API client.

These tests make REAL API calls to Strava and require valid credentials.
They are skipped by default and must be run explicitly with:
    pytest -m integration

To run all tests including integration:
    pytest -m ""
"""

import os
import pytest
from dotenv import load_dotenv

from src.strava.client import StravaClient


# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)


# Skip all integration tests by default unless explicitly requested
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def strava_client():
    """Create a real Strava client with credentials from .env file."""
    # Check if credentials are available
    if not os.environ.get("STRAVA_ACCESS_TOKEN"):
        pytest.skip("STRAVA_ACCESS_TOKEN not set in environment")
    
    return StravaClient()


# ---------------------------------------------------------------------------
# Authentication & Athlete
# ---------------------------------------------------------------------------

def test_get_athlete(strava_client):
    """Test fetching authenticated athlete profile from real API."""
    athlete = strava_client.get_athlete()
    
    # Verify response structure
    assert "id" in athlete
    assert "firstname" in athlete
    assert "lastname" in athlete
    assert isinstance(athlete["id"], int)
    assert isinstance(athlete["firstname"], str)
    
    print(f"\n✅ Authenticated as {athlete['firstname']} {athlete['lastname']} (ID: {athlete['id']})")


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

def test_get_activities(strava_client):
    """Test fetching recent activities from real API."""
    activities = strava_client.get_activities(per_page=5)
    
    # Verify response structure
    assert isinstance(activities, list)
    
    if len(activities) > 0:
        activity = activities[0]
        assert "id" in activity
        assert "name" in activity
        assert "type" in activity
        assert "distance" in activity
        
        print(f"\n✅ Retrieved {len(activities)} activities")
        for act in activities[:3]:  # Show first 3
            print(f"  - {act['name']} ({act['type']})")
    else:
        print("\n No activities found for this athlete")


def test_get_activities_pagination(strava_client):
    """Test activity pagination works correctly."""
    page1 = strava_client.get_activities(page=1, per_page=2)
    page2 = strava_client.get_activities(page=2, per_page=2)
    
    # Pages should be different (unless athlete has < 3 activities)
    if len(page1) >= 2 and len(page2) > 0:
        assert page1[0]["id"] != page2[0]["id"], "Pagination should return different activities"
        print(f"\n✅ Pagination working: page 1 has {len(page1)} activities, page 2 has {len(page2)}")


def test_get_specific_activity(strava_client):
    """Test fetching a specific activity by ID."""
    # First get an activity ID
    activities = strava_client.get_activities(per_page=1)
    
    if len(activities) == 0:
        pytest.skip("No activities available to test")
    
    activity_id = activities[0]["id"]
    
    # Fetch the specific activity
    activity = strava_client.get_activity(activity_id)
    
    # Verify detailed response
    assert activity["id"] == activity_id
    assert "name" in activity
    assert "type" in activity
    assert "moving_time" in activity
    assert "distance" in activity
    
    print(f"\n✅ Retrieved activity: {activity['name']} (ID: {activity_id})")
    print(f"   Type: {activity['type']}, Distance: {activity.get('distance', 'N/A')}m")


# ---------------------------------------------------------------------------
# Activity Streams
# ---------------------------------------------------------------------------

def test_get_activity_streams(strava_client):
    """Test fetching time-series data streams for an activity."""
    # First get an activity ID
    activities = strava_client.get_activities(per_page=5)
    
    if len(activities) == 0:
        pytest.skip("No activities available to test")
    
    activity_id = activities[0]["id"]
    
    # Fetch streams
    streams = strava_client.get_activity_streams(activity_id)
    
    # Verify response structure
    assert isinstance(streams, dict)
    
    # Common stream types (not all activities have all streams)
    possible_streams = ["time", "distance", "heartrate", "watts", "altitude", "cadence"]
    found_streams = [s for s in possible_streams if s in streams]
    
    print(f"\n✅ Retrieved streams for activity {activity_id}")
    print(f"   Available streams: {', '.join(found_streams)}")
    
    # Verify at least some stream data exists
    assert len(found_streams) > 0, "Expected at least one stream type"


def test_get_activity_streams_custom_types(strava_client):
    """Test fetching specific stream types."""
    activities = strava_client.get_activities(per_page=1)
    
    if len(activities) == 0:
        pytest.skip("No activities available to test")
    
    activity_id = activities[0]["id"]
    
    # Request only specific streams
    streams = strava_client.get_activity_streams(
        activity_id,
        stream_types=["time", "distance"]
    )
    
    assert isinstance(streams, dict)
    print(f"\n✅ Retrieved custom streams for activity {activity_id}")


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------

def test_invalid_activity_id_raises_error(strava_client):
    """Test that requesting invalid activity ID raises appropriate error."""
    import requests
    
    # Use a very unlikely activity ID
    with pytest.raises(requests.exceptions.HTTPError) as exc_info:
        strava_client.get_activity(99999999999)
    
    # Should be 404 Not Found
    assert exc_info.value.response.status_code == 404
    print("\n✅ Correctly raises HTTPError for invalid activity ID")


def test_per_page_limit_validation():
    """Test that per_page exceeding 200 raises ValueError."""
    client = StravaClient()
    
    with pytest.raises(ValueError, match="cannot exceed 200"):
        client.get_activities(per_page=201)
    
    print("\n✅ Correctly validates per_page limit")


# ---------------------------------------------------------------------------
# Token Refresh (if configured)
# ---------------------------------------------------------------------------

def test_token_refresh_if_configured(strava_client):
    """Test token refresh if refresh credentials are available."""
    if not strava_client._refresh_token:
        pytest.skip("Refresh token not configured")
    
    # Force refresh by calling the internal method
    old_token = strava_client._access_token
    strava_client._refresh_access_token()
    new_token = strava_client._access_token
    
    # Token should have changed (or could be the same if Strava returns same token)
    assert new_token is not None
    assert len(new_token) > 0
    
    # Verify new token works by making a request
    athlete = strava_client.get_athlete()
    assert "id" in athlete
    
    print(f"\n✅ Token refresh successful")
    print(f"   Old token: {old_token[:20]}...")
    print(f"   New token: {new_token[:20]}...")
