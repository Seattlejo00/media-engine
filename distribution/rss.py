"""
RSS / Podcast feed generator.
Generates a standard RSS 2.0 podcast feed compatible with
Spotify, Apple Podcasts, Google Podcasts, etc.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from feedgen.feed import FeedGenerator

import config

logger = logging.getLogger(__name__)


def generate_feed(episodes: list[dict], output_dir: Path) -> Path:
    """
    Generate/update the podcast RSS feed.

    Args:
        episodes: List of episode dicts with keys:
            - title, description, date, audio_url, duration_seconds, file_size_bytes
        output_dir: Where to save the feed.xml

    Returns:
        Path to the generated feed.xml
    """
    fg = FeedGenerator()
    fg.load_extension("podcast")

    # Podcast metadata
    fg.title(config.PODCAST_TITLE)
    fg.description(config.PODCAST_DESCRIPTION)
    fg.link(href=config.RSS_FEED_URL, rel="self")
    fg.language("en")
    fg.podcast.itunes_category("Technology")
    fg.podcast.itunes_author("Claude & ChatGPT")
    fg.podcast.itunes_summary(config.PODCAST_DESCRIPTION)
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_type("episodic")

    # Add episodes (newest first)
    for ep in sorted(episodes, key=lambda e: e["date"], reverse=True):
        fe = fg.add_entry()
        fe.id(ep.get("audio_url", ep["title"]))
        fe.title(ep["title"])
        fe.description(ep["description"])
        fe.published(ep["date"].replace(tzinfo=timezone.utc) if isinstance(ep["date"], datetime) else ep["date"])

        if ep.get("audio_url"):
            fe.enclosure(
                url=ep["audio_url"],
                length=str(ep.get("file_size_bytes", 0)),
                type="audio/mpeg",
            )

        if ep.get("duration_seconds"):
            minutes = int(ep["duration_seconds"] // 60)
            seconds = int(ep["duration_seconds"] % 60)
            fe.podcast.itunes_duration(f"{minutes}:{seconds:02d}")

    # Write feed
    output_dir.mkdir(parents=True, exist_ok=True)
    feed_path = output_dir / "feed.xml"
    fg.rss_file(str(feed_path), pretty=True)

    logger.info(f"RSS feed generated: {feed_path}")
    return feed_path
