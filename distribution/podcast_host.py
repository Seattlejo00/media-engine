"""
Podcast audio hosting.
Uploads episode MP3s to cloud storage (Cloudflare R2 or S3-compatible)
so Spotify / Apple Podcasts / etc. can serve them from the RSS feed.

R2 is recommended: free egress, ~$0.015/GB/month storage.
A 30-min episode is ~30MB = less than $0.01/month.
"""

import logging
import mimetypes
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def hosting_configured() -> bool:
    """True when the R2 credentials needed for podcast hosting are set."""
    return all([config.R2_BUCKET_NAME, config.R2_ACCESS_KEY_ID])


def _r2_client():
    """Build an S3 client pointed at R2."""
    import boto3
    from botocore.config import Config as BotoConfig

    # R2 uses the S3 API
    return boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT_URL,
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        config=BotoConfig(
            signature_version="s3v4",
            region_name="auto",
        ),
    )


def download_feed_state(dest_path: Path) -> bool:
    """
    Pull the persisted episode list (feed_episodes.json) from R2.

    The pipeline runs on ephemeral CI machines, so R2 is the source of
    truth for feed history. Returns True if a copy was downloaded.
    """
    if not hosting_configured():
        return False
    try:
        s3 = _r2_client()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(config.R2_BUCKET_NAME, "feed/feed_episodes_v2.json", str(dest_path))
        logger.info("Downloaded feed history from R2")
        return True
    except Exception as e:
        # First episode ever (404) or transient failure — start fresh
        logger.info(f"No feed history downloaded from R2 ({e}) — starting fresh")
        return False


def upload_feed(feed_xml_path: Path, feed_state_path: Path) -> str | None:
    """
    Publish feed.xml (and the episode-list state file) to R2.

    Returns the public feed URL, which is what gets submitted to
    Spotify / Apple Podcasts.
    """
    if not hosting_configured():
        return None
    try:
        s3 = _r2_client()
        s3.upload_file(
            str(feed_xml_path), config.R2_BUCKET_NAME, "feed.xml",
            ExtraArgs={
                "ContentType": "application/rss+xml",
                "CacheControl": "public, max-age=300",  # podcast apps poll this
            },
        )
        if feed_state_path.exists():
            s3.upload_file(
                str(feed_state_path), config.R2_BUCKET_NAME, "feed/feed_episodes_v2.json",
                ExtraArgs={"ContentType": "application/json"},
            )
        feed_url = f"{config.R2_PUBLIC_URL}/feed.xml"
        logger.info(f"Published podcast feed: {feed_url}")
        return feed_url
    except Exception as e:
        logger.error(f"Feed upload failed: {e}")
        return None


def upload_social_clip(clip_path: Path, date_str: str, idx: int) -> str | None:
    """
    Stage a clip in R2 and return its public URL.

    Instagram's API fetches videos from a URL rather than accepting
    uploads, so clips get a public home here first.
    """
    if not hosting_configured():
        return None
    try:
        s3 = _r2_client()
        object_key = f"social/{date_str}/clip_{idx}.mp4"
        s3.upload_file(
            str(clip_path), config.R2_BUCKET_NAME, object_key,
            ExtraArgs={"ContentType": "video/mp4",
                       "CacheControl": "public, max-age=86400"},
        )
        return f"{config.R2_PUBLIC_URL}/{object_key}"
    except Exception as e:
        logger.error(f"Social clip upload failed: {e}")
        return None


def upload_episode_audio(
    audio_path: Path,
    date_str: str,
) -> str | None:
    """
    Upload episode MP3 to cloud storage.

    Returns the public URL if successful, None otherwise.
    """
    if not hosting_configured():
        logger.warning(
            "Podcast hosting not configured (R2_BUCKET_NAME / R2_ACCESS_KEY_ID "
            "missing) — skipping audio upload. RSS feed will have no audio URL."
        )
        return None

    try:
        s3 = _r2_client()

        # Upload with a predictable key
        object_key = f"episodes/{date_str}/episode.mp3"
        content_type = mimetypes.guess_type(str(audio_path))[0] or "audio/mpeg"

        s3.upload_file(
            str(audio_path),
            config.R2_BUCKET_NAME,
            object_key,
            ExtraArgs={
                "ContentType": content_type,
                "CacheControl": "public, max-age=31536000",  # immutable
            },
        )

        # Build public URL
        public_url = f"{config.R2_PUBLIC_URL}/{object_key}"

        logger.info(f"Uploaded episode audio: {public_url}")
        return public_url

    except Exception as e:
        logger.error(f"Podcast audio upload failed: {e}")
        return None
