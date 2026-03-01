"""
YouTube upload.
Uploads full episodes and clips to YouTube via the Data API v3.
"""

import logging
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config

logger = logging.getLogger(__name__)


def _get_youtube_client():
    """Build authenticated YouTube API client."""
    creds = Credentials(
        token=None,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str] | None = None,
    is_short: bool = False,
    privacy: str = "public",
) -> str | None:
    """
    Upload a video to YouTube.

    Args:
        video_path: Path to the MP4 file
        title: Video title
        description: Video description
        tags: Optional list of tags
        is_short: If True, adds #Shorts to title
        privacy: "public", "unlisted", or "private"

    Returns:
        Video ID if successful, None otherwise.
    """
    if not all([config.YOUTUBE_CLIENT_ID, config.YOUTUBE_REFRESH_TOKEN]):
        logger.warning("YouTube credentials not configured, skipping upload")
        return None

    if is_short:
        title = f"{title} #Shorts"

    if tags is None:
        tags = ["AI", "podcast", "ChatGPT", "Claude", "artificial intelligence",
                "tech news", "AI daily"]

    try:
        youtube = _get_youtube_client()

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags,
                "categoryId": "28",  # Science & Technology
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MB chunks
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Upload progress: {int(status.progress() * 100)}%")

        video_id = response["id"]
        logger.info(f"Uploaded to YouTube: https://youtube.com/watch?v={video_id}")
        return video_id

    except Exception as e:
        logger.error(f"YouTube upload failed: {e}")
        return None


def upload_episode(
    video_path: Path, script: dict, date_str: str
) -> str | None:
    """Upload a full episode."""
    title = f"{script.get('title', 'The AI Daily')} | {date_str}"
    description = (
        f"{script.get('description', '')}\n\n"
        f"The AI Daily — a podcast hosted by ChatGPT and Claude.\n"
        f"Two AIs discuss the day's biggest stories, as themselves.\n\n"
        f"New episodes daily.\n\n"
        f"#AI #ChatGPT #Claude #Podcast #TechNews"
    )
    return upload_video(video_path, title, description)


def upload_clip(
    clip_path: Path, clip_title: str, episode_id: str | None = None
) -> str | None:
    """Upload a short clip."""
    description = f"From today's episode of The AI Daily\n"
    if episode_id:
        description += f"Full episode: https://youtube.com/watch?v={episode_id}\n"
    description += "\n#AI #ChatGPT #Claude #Shorts"

    return upload_video(clip_path, clip_title, description, is_short=True)
