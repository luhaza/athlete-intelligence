from client import StravaClient
from dotenv import load_dotenv
import requests
import os

# Load .env from project root
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(env_path)

client = StravaClient()
athlete = client.get_athlete()
print(f"Authenticated as {athlete['firstname']} {athlete['lastname']} (ID {athlete['id']})")

# Fetch some activities
try:
    activities = client.get_activities(per_page=5)
    print(f"\nRecent activities: {len(activities)}")
    for activity in activities:
        print(f"  - {activity['name']} ({activity['type']})")
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 401:
        error_data = e.response.json()
        print(f"\n⚠️  Authorization Error: {error_data}")
        print("\nYour access token is missing the 'activity:read_all' scope.")
        print("Please re-authorize with the proper scopes to read activities.")
    else:
        raise
