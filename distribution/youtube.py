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


def set_thumbnail(video_id: str, thumbnail_path: Path) -> bool:
    """
    Set a custom thumbnail for a YouTube video.

    Requires the channel to be verified for custom thumbnails.
    Returns True if successful, False otherwise.
    """
    if not video_id or not thumbnail_path or not thumbnail_path.exists():
        return False

    try:
        youtube = _get_youtube_client()

        media = MediaFileUpload(
            str(thumbnail_path),
            mimetype="image/png",
            resumable=False,
        )

        youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        ).execute()

        logger.info(f"Custom thumbnail set for video {video_id}")
        return True

    except Exception as e:
        logger.warning(f"Failed to set custom thumbnail: {e}")
        return False


def _roster_tags(roster: list[str] | None = None) -> list[str]:
    """Build dynamic tags based on the episode roster."""
    base = ["AI", "podcast", "artificial intelligence", "tech news", "AI daily"]
    if roster is None:
        roster = config.get_hosts()
    for name in roster:
        speaker = config.SPEAKERS.get(name)
        if speaker:
            base.append(name)
            base.append(speaker["company"])
    return base


def _roster_description(roster: list[str] | None = None) -> str:
    """Build a 'hosted by …' line from the roster."""
    if roster is None:
        roster = config.get_hosts()
    if len(roster) == 1:
        return f"Hosted by {roster[0]}."
    return f"Hosted by {', '.join(roster[:-1])} and {roster[-1]}."


def upload_episode(
    video_path: Path, script: dict, date_str: str,
    roster: list[str] | None = None,
    thumbnail_path: Path | None = None,
) -> str | None:
    """Upload a full episode with optional custom thumbnail."""
    # Prefer YouTube-optimized title, fall back to script title
    title = script.get("youtube_title") or f"{script.get('title', 'The Context Window')} | {date_str}"
    hosted_by = _roster_description(roster)
    description = (
        f"{script.get('description', '')}\n\n"
        f"The Context Window — {hosted_by}\n"
        f"AIs discuss the day's biggest stories, as themselves.\n\n"
        f"New episodes daily.\n\n"
        f"#AI #Podcast #TechNews"
    )
    tags = _roster_tags(roster)
    video_id = upload_video(video_path, title, description, tags=tags)

    # Set custom thumbnail if available
    if video_id and thumbnail_path:
        set_thumbnail(video_id, thumbnail_path)

    return video_id


def upload_clip(
    clip_path: Path, clip_title: str, episode_id: str | None = None,
    roster: list[str] | None = None,
) -> str | None:
    """Upload a short clip."""
    description = f"From today's episode of The Context Window\n"
    if episode_id:
        description += f"Full episode: https://youtube.com/watch?v={episode_id}\n"
    names = " #".join(roster) if roster else "ChatGPT #Claude"
    description += f"\n#{names} #AI #Shorts"

    tags = _roster_tags(roster)
    return upload_video(clip_path, clip_title, description, tags=tags, is_short=True)
