"""
Social media distribution.
Posts clips and episode announcements to X/Twitter and TikTok.
"""

import logging
from pathlib import Path

import config

logger = logging.getLogger(__name__)


# --- Twitter/X ---

def post_to_twitter(
    text: str,
    media_path: Path | None = None,
) -> str | None:
    """
    Post to X/Twitter with optional media attachment.

    Returns tweet ID if successful, None otherwise.
    """
    if not all([config.TWITTER_API_KEY, config.TWITTER_ACCESS_TOKEN]):
        logger.warning("Twitter credentials not configured, skipping post")
        return None

    try:
        import tweepy

        client = tweepy.Client(
            consumer_key=config.TWITTER_API_KEY,
            consumer_secret=config.TWITTER_API_SECRET,
            access_token=config.TWITTER_ACCESS_TOKEN,
            access_token_secret=config.TWITTER_ACCESS_SECRET,
        )

        media_id = None
        if media_path and media_path.exists():
            # v1.1 API needed for media upload
            auth = tweepy.OAuth1UserHandler(
                config.TWITTER_API_KEY,
                config.TWITTER_API_SECRET,
                config.TWITTER_ACCESS_TOKEN,
                config.TWITTER_ACCESS_SECRET,
            )
            api_v1 = tweepy.API(auth)
            media = api_v1.media_upload(str(media_path))
            media_id = media.media_id

        response = client.create_tweet(
            text=text[:280],
            media_ids=[media_id] if media_id else None,
        )

        tweet_id = response.data["id"]
        logger.info(f"Posted to Twitter: {tweet_id}")
        return tweet_id

    except Exception as e:
        logger.error(f"Twitter post failed: {e}")
        return None


def post_episode_to_twitter(script: dict, youtube_url: str | None = None) -> str | None:
    """Post episode announcement to Twitter."""
    title = script.get("title", "New Episode")
    text = f"🎙️ New episode of The AI Daily\n\n{title}\n\n"

    if youtube_url:
        text += f"Watch: {youtube_url}\n\n"

    text += "#AI #ChatGPT #Claude #Podcast"

    return post_to_twitter(text)


def post_clip_to_twitter(
    clip_path: Path, clip_title: str, episode_url: str | None = None
) -> str | None:
    """Post a clip to Twitter with video."""
    text = f"🔥 {clip_title}\n\nFrom today's AI Daily"
    if episode_url:
        text += f"\n\nFull ep: {episode_url}"

    return post_to_twitter(text, clip_path)


# --- TikTok ---

def upload_to_tiktok(
    video_path: Path,
    title: str,
) -> str | None:
    """
    Upload video to TikTok.

    Note: TikTok's API for direct video upload requires
    Creator Tools access. This is a placeholder that logs
    the intent — actual implementation depends on your
    TikTok developer access level.
    """
    if not config.TIKTOK_ACCESS_TOKEN:
        logger.warning("TikTok credentials not configured, skipping upload")
        return None

    # TikTok direct publish API
    # Requires: Content Posting API access (apply at developers.tiktok.com)
    try:
        import requests

        # Step 1: Initialize upload
        resp = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={
                "Authorization": f"Bearer {config.TIKTOK_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "post_info": {
                    "title": title[:150],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_comment": False,
                    "disable_duet": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_path.stat().st_size,
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        upload_url = data["data"]["upload_url"]
        publish_id = data["data"]["publish_id"]

        # Step 2: Upload video file
        with open(video_path, "rb") as f:
            upload_resp = requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes 0-{video_path.stat().st_size - 1}/{video_path.stat().st_size}",
                },
                data=f,
                timeout=120,
            )
            upload_resp.raise_for_status()

        logger.info(f"Uploaded to TikTok: publish_id={publish_id}")
        return publish_id

    except Exception as e:
        logger.error(f"TikTok upload failed: {e}")
        return None
