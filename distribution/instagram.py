"""
Instagram Reels posting via the Instagram API (Instagram Login).

The Graph API can't accept file uploads — it FETCHES the video from a
public URL — so clips are staged in the R2 bucket first. Requires an
Instagram professional (Creator/Business) account connected to a Meta
app with the instagram_business_content_publish scope; see SETUP_TODO.
"""

import logging
import time

import config
from distribution.gh_secrets import persist_secret

logger = logging.getLogger(__name__)

GRAPH = "https://graph.instagram.com/v21.0"
POLL_INTERVAL_S = 5
POLL_ATTEMPTS = 48  # ~4 minutes for Instagram to fetch + process the video


def instagram_configured() -> bool:
    return bool(config.INSTAGRAM_USER_ID and config.INSTAGRAM_ACCESS_TOKEN)


def refresh_access_token() -> None:
    """
    Refresh the 60-day long-lived token (allowed once it's >24h old) and
    persist it back to the repo secret so the chain never breaks.
    """
    import requests

    try:
        resp = requests.get(
            "https://graph.instagram.com/refresh_access_token",
            params={
                "grant_type": "ig_refresh_token",
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
            timeout=30,
        )
        if not resp.ok:
            # A token younger than 24h can't be refreshed yet — that's fine
            logger.info(f"IG token not refreshed ({resp.json().get('error', {}).get('message', resp.text[:120])})")
            return
        data = resp.json()
        new_token = data.get("access_token")
        if new_token and new_token != config.INSTAGRAM_ACCESS_TOKEN:
            config.INSTAGRAM_ACCESS_TOKEN = new_token
            if not persist_secret("INSTAGRAM_ACCESS_TOKEN", new_token):
                days = int(data.get("expires_in", 0)) // 86400
                logger.warning(
                    f"Instagram token refreshed (valid ~{days}d) but could NOT "
                    "be persisted — add a GH_SECRETS_PAT secret (fine-grained "
                    "PAT, Secrets: write) or re-issue the token manually before "
                    "it expires."
                )
    except Exception as e:
        logger.warning(f"IG token refresh check failed: {e}")


def post_reel(video_url: str, caption: str) -> str | None:
    """
    Publish a Reel from a public video URL.

    Three steps: create a media container, wait for Instagram to fetch
    and process the video, then publish. Returns the media ID.
    """
    import requests

    token = config.INSTAGRAM_ACCESS_TOKEN
    user_id = config.INSTAGRAM_USER_ID

    try:
        # 1. Create the media container
        resp = requests.post(
            f"{GRAPH}/{user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption[:2200],
                "share_to_feed": "true",
                "access_token": token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        container_id = resp.json()["id"]

        # 2. Poll until Instagram has fetched + processed the video
        for _ in range(POLL_ATTEMPTS):
            time.sleep(POLL_INTERVAL_S)
            status = requests.get(
                f"{GRAPH}/{container_id}",
                params={"fields": "status_code", "access_token": token},
                timeout=30,
            ).json()
            code = status.get("status_code")
            if code == "FINISHED":
                break
            if code == "ERROR":
                logger.error(f"Instagram rejected the video: {status}")
                return None
        else:
            logger.error("Instagram processing timed out")
            return None

        # 3. Publish
        resp = requests.post(
            f"{GRAPH}/{user_id}/media_publish",
            data={"creation_id": container_id, "access_token": token},
            timeout=30,
        )
        resp.raise_for_status()
        media_id = resp.json()["id"]
        logger.info(f"Posted Reel to Instagram: {media_id}")
        return media_id

    except Exception as e:
        logger.error(f"Instagram post failed: {e}")
        return None
