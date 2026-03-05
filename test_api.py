#!/usr/bin/env python3
"""Systematic API testing script."""

import requests
import json
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

def print_test(name: str, result: str):
    """Print test result with formatting."""
    status = "✓" if result == "PASS" else "✗"
    print(f"{status} {name}: {result}")

def test_endpoint(name: str, url: str, expected_keys: list = None) -> str:
    """Test an endpoint and return result."""
    try:
        response = requests.get(url, timeout=5)
        
        if response.status_code != 200:
            return f"FAIL - Status {response.status_code}"
        
        data = response.json()
        
        if expected_keys:
            missing = [k for k in expected_keys if k not in data]
            if missing:
                return f"FAIL - Missing keys: {missing}"
        
        return "PASS"
    except requests.exceptions.ConnectionError:
        return "FAIL - Connection refused (server not running?)"
    except requests.exceptions.Timeout:
        return "FAIL - Timeout"
    except json.JSONDecodeError:
        return "FAIL - Invalid JSON response"
    except Exception as e:
        return f"FAIL - {str(e)}"

print("=" * 60)
print("API FUNCTIONALITY TEST SUITE")
print("=" * 60)
print()

# Test 1: Health endpoints
print("HEALTH ENDPOINTS:")
print_test("GET /", test_endpoint("Root", f"{BASE_URL}/", ["status", "app", "version"]))
print_test("GET /health", test_endpoint("Health", f"{BASE_URL}/health", ["status", "database"]))
print()

# Test 2: Athlete endpoints
print("ATHLETE ENDPOINTS:")
print_test("GET /athlete", test_endpoint("Athlete Profile", f"{BASE_URL}/athlete", ["strava_athlete_id", "full_name"]))
print_test("GET /athlete/stats", test_endpoint("Athlete Stats", f"{BASE_URL}/athlete/stats", ["total_activities", "total_distance_miles"]))
print()

# Test 3: Activities list
print("ACTIVITIES LIST:")
print_test("GET /activities", test_endpoint("List Activities", f"{BASE_URL}/activities", ["total", "activities"]))
print_test("GET /activities?limit=2", test_endpoint("List with limit", f"{BASE_URL}/activities?limit=2", ["total", "limit", "activities"]))
print_test("GET /activities?sport_type=Run", test_endpoint("Filter by sport", f"{BASE_URL}/activities?sport_type=Run"))
print()

# Test 4: Get a specific activity ID
print("Getting activity ID for detailed tests...")
try:
    response = requests.get(f"{BASE_URL}/activities?limit=1")
    if response.status_code == 200:
        data = response.json()
        if data['activities']:
            activity_id = data['activities'][0]['strava_activity_id']
            print(f"  Using activity ID: {activity_id}")
            print()
            
            # Test 5: Single activity
            print("SINGLE ACTIVITY:")
            print_test(f"GET /activities/{activity_id}", 
                      test_endpoint("Activity Detail", f"{BASE_URL}/activities/{activity_id}", 
                                  ["name", "distance", "distance_miles", "pace_per_mile"]))
            print()
            
            # Test 6: Activity streams
            print("ACTIVITY STREAMS:")
            print_test(f"GET /activities/{activity_id}/streams", 
                      test_endpoint("All Streams", f"{BASE_URL}/activities/{activity_id}/streams", 
                                  ["activity_id", "streams"]))
            print_test(f"GET /activities/{activity_id}/streams?types=heartrate", 
                      test_endpoint("Specific Stream", f"{BASE_URL}/activities/{activity_id}/streams?types=heartrate"))
            print()
            
            # Test 7: Activity laps
            print("ACTIVITY LAPS:")
            print_test(f"GET /activities/{activity_id}/laps", 
                      test_endpoint("Activity Laps", f"{BASE_URL}/activities/{activity_id}/laps"))
            print()
        else:
            print("  No activities found in database!")
            print()
except Exception as e:
    print(f"  Error getting activity ID: {e}")
    print()

# Test 8: Error handling
print("ERROR HANDLING:")
print_test("GET /activities/999999999 (non-existent)", 
          "PASS" if requests.get(f"{BASE_URL}/activities/999999999").status_code == 404 else "FAIL")
print_test("GET /activities?sport_type=Invalid;DROP", 
          "PASS" if requests.get(f"{BASE_URL}/activities?sport_type=Invalid;DROP").status_code in [200, 400] else "FAIL")
print()

# Test 9: Input validation
print("INPUT VALIDATION:")
response = requests.get(f"{BASE_URL}/activities?limit=500")
print_test("Limit > 100 rejected", "PASS" if response.status_code == 422 else f"FAIL - Got {response.status_code}")

response = requests.get(f"{BASE_URL}/activities?limit=-1")
print_test("Negative limit rejected", "PASS" if response.status_code == 422 else f"FAIL - Got {response.status_code}")

# Test with very long sport type
long_type = "A" * 100
response = requests.get(f"{BASE_URL}/activities?sport_type={long_type}")
print_test("Long sport_type rejected", "PASS" if response.status_code in [400, 422] else f"FAIL - Got {response.status_code}")

print()
print("=" * 60)
print("TEST SUITE COMPLETE")
print("=" * 60)
