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


def upload_episode_audio(
    audio_path: Path,
    date_str: str,
) -> str | None:
    """
    Upload episode MP3 to cloud storage.

    Returns the public URL if successful, None otherwise.
    """
    if not all([config.R2_BUCKET_NAME, config.R2_ACCESS_KEY_ID]):
        logger.warning(
            "Podcast hosting not configured (R2_BUCKET_NAME / R2_ACCESS_KEY_ID "
            "missing) — skipping audio upload. RSS feed will have no audio URL."
        )
        return None

    try:
        import boto3
        from botocore.config import Config as BotoConfig

        # R2 uses the S3 API
        s3 = boto3.client(
            "s3",
            endpoint_url=config.R2_ENDPOINT_URL,
            aws_access_key_id=config.R2_ACCESS_KEY_ID,
            aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
            config=BotoConfig(
                signature_version="s3v4",
                region_name="auto",
            ),
        )

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
