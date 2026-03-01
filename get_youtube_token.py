"""
One-time script to get a YouTube OAuth refresh token.
Run this, sign in via browser, and it prints the refresh token to paste into .env
"""

from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv
import os

load_dotenv(override=True)

client_id = os.getenv("YOUTUBE_CLIENT_ID")
client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

if not client_id or not client_secret:
    print("ERROR: Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env first")
    exit(1)

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    },
    scopes=["https://www.googleapis.com/auth/youtube.upload"],
)

creds = flow.run_local_server(port=8091, prompt="consent", access_type="offline")

print("\n" + "=" * 60)
print("SUCCESS! Paste this into your .env on the YOUTUBE_REFRESH_TOKEN line:")
print("=" * 60)
print(f"\nYOUTUBE_REFRESH_TOKEN={creds.refresh_token}\n")
