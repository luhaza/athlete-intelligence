"""Exchange Strava authorization code for access and refresh tokens."""

import requests
import sys

CLIENT_ID = "118437"
CLIENT_SECRET = "369f3b44f3c408ccd3e25d738d693f69a2081707"

if len(sys.argv) != 2:
    print("Usage: python get_tokens.py <authorization_code>")
    print("\nGet your authorization code by visiting:")
    print(f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=read,activity:read_all")
    sys.exit(1)

auth_code = sys.argv[1]

print("Exchanging authorization code for tokens...")
response = requests.post(
    "https://www.strava.com/oauth/token",
    data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "grant_type": "authorization_code",
    },
)

if response.status_code != 200:
    print(f"Error: {response.status_code}")
    print(response.json())
    sys.exit(1)

data = response.json()

print("\n✅ Success! Update your .env file with these values:\n")
print(f"STRAVA_ACCESS_TOKEN={data['access_token']}")
print(f"STRAVA_REFRESH_TOKEN={data['refresh_token']}")
print(f"STRAVA_EXPIRES_AT={data['expires_at']}")
print(f"\nScopes granted: {data.get('scope', 'N/A')}")
