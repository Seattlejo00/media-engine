"""
One-time script to get a TikTok OAuth refresh token.

Prereqs (from your app page at developers.tiktok.com):
  - App with Login Kit + Content Posting API products
  - Scopes approved: user.info.basic, video.upload, video.publish
  - A registered Redirect URI (any URL you control — nothing needs to be
    deployed there; you'll just copy the address you land on back here)

Put these in .env first:
  TIKTOK_CLIENT_KEY=...
  TIKTOK_CLIENT_SECRET=...
  TIKTOK_REDIRECT_URI=...   (must EXACTLY match the one registered on the app)

Then:  python get_tiktok_token.py
Sign in with the TikTok account that should post the clips, approve, and
paste the URL you get redirected to. The script prints the refresh token
to store as the TIKTOK_REFRESH_TOKEN repo secret.
"""

import os
import secrets
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

client_key = os.getenv("TIKTOK_CLIENT_KEY")
client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
redirect_uri = os.getenv("TIKTOK_REDIRECT_URI")

if not all([client_key, client_secret, redirect_uri]):
    print("ERROR: Set TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET and TIKTOK_REDIRECT_URI in .env first")
    exit(1)

state = secrets.token_urlsafe(16)
auth_url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(
    {
        "client_key": client_key,
        "scope": "user.info.basic,video.upload,video.publish",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    }
)

print("Opening TikTok authorization page...")
print(f"(If the browser doesn't open, visit this URL yourself)\n\n{auth_url}\n")
webbrowser.open(auth_url)

print("Sign in with the account that should post the clips and approve.")
print("You'll be redirected to your redirect URI (the page itself may 404 — that's fine).")
pasted = input("\nPaste the FULL URL from your browser's address bar after the redirect:\n> ").strip()

query = parse_qs(urlparse(pasted).query)
if query.get("state", [None])[0] != state:
    print("WARNING: state mismatch — make sure you pasted the URL from THIS run.")
code = query.get("code", [None])[0]
if not code:
    print(f"ERROR: no ?code= found in that URL. Got params: {list(query)}")
    exit(1)

resp = requests.post(
    "https://open.tiktokapis.com/v2/oauth/token/",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    },
    timeout=30,
)
data = resp.json()

if "refresh_token" not in data:
    print(f"ERROR: token exchange failed: {data}")
    exit(1)

print("\nSuccess! Add this as a repo secret (and .env for local runs):\n")
print(f"TIKTOK_REFRESH_TOKEN={data['refresh_token']}")
print(f"\n(access token, expires in {data.get('expires_in', '?')}s — the pipeline")
print("mints fresh ones automatically, you don't need to save it)")
print(f"\nGranted scopes: {data.get('scope', '?')}")
