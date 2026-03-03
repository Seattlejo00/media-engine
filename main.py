"""
The AI Daily — Media Engine
Main orchestrator that runs the full pipeline:
  Topics -> Script -> TTS -> Audio -> Video -> Clips -> Distribute

Usage:
    python main.py                  # Run once (generate today's episode)
    python main.py --schedule       # Run daily on a schedule
    python main.py --script-only    # Generate script only (no audio/video)
    python main.py --dry-run        # Discover topics but don't generate anything
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import config
from pipeline.topics import discover_topics
from pipeline.script import generate_script, save_script
from pipeline.tts import synthesize_script
from pipeline.audio import assemble_episode, get_episode_duration
from pipeline.video import generate_landscape_video
from pipeline.clips import identify_clip_segments, extract_clips
from pipeline.cost_tracker import tracker
from distribution.youtube import upload_episode, upload_clip
from distribution.rss import generate_feed
from distribution.social import post_episode_to_twitter, post_clip_to_twitter

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("media_engine.log"),
    ],
)
logger = logging.getLogger("media-engine")


def run_pipeline(
    script_only: bool = False,
    dry_run: bool = False,
    guest: str | None = None,
    roundtable: bool = False,
) -> dict:
    """
    Execute the full episode generation pipeline.

    Returns a summary dict with paths and IDs.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    episode_dir = config.OUTPUT_DIR / date_str
    episode_dir.mkdir(parents=True, exist_ok=True)

    # Determine today's episode roster
    if roundtable:
        roster = config.get_hosts() + config.get_guests()
    elif guest:
        if guest not in config.SPEAKERS:
            raise ValueError(
                f"Unknown guest: {guest}. "
                f"Available: {config.get_all_guests()}"
            )
        if not config.speaker_has_api_key(guest):
            raise ValueError(
                f"{guest} has no API key configured — guests can't speak "
                f"unless they write their own lines. Add the API key to .env first."
            )
        roster = config.get_hosts() + [guest]
    else:
        roster = config.get_episode_roster()

    is_guest_episode = len(roster) > len(config.get_hosts())

    summary = {"date": date_str, "status": "started", "roster": roster}

    if is_guest_episode:
        guests = [s for s in roster if config.SPEAKERS[s]["role"] == "guest"]
        logger.info(f"Guest episode! Today's guests: {guests}")

    # === STEP 1: Discover Topics ===
    logger.info("=" * 60)
    logger.info("STEP 1: Discovering topics...")
    logger.info("=" * 60)

    topics = discover_topics()

    if not topics:
        logger.error("No topics found. Aborting.")
        summary["status"] = "failed"
        summary["error"] = "no_topics"
        return summary

    # Save topics
    topics_path = episode_dir / "topics.json"
    topics_path.write_text(json.dumps(topics, indent=2), encoding="utf-8")
    summary["topics"] = [t["title"] for t in topics]
    logger.info(f"Topics: {[t['title'] for t in topics]}")

    if dry_run:
        logger.info("Dry run — stopping after topic discovery.")
        summary["status"] = "dry_run_complete"
        return summary

    # === STEP 2: Generate Script ===
    logger.info("=" * 60)
    logger.info("STEP 2: Generating script...")
    logger.info("=" * 60)

    script = generate_script(topics, roster=roster)
    script_path = save_script(script, episode_dir)
    summary["script_path"] = str(script_path)
    summary["episode_title"] = script.get("title", "Untitled")
    logger.info(f"Episode: {script.get('title', 'Untitled')}")

    # Save readable transcript
    _save_transcript(script, episode_dir, date_str)

    if script_only:
        logger.info("Script-only mode — stopping after script generation.")
        summary["status"] = "script_complete"
        return summary

    # === STEP 3: Text-to-Speech ===
    logger.info("=" * 60)
    logger.info("STEP 3: Synthesizing speech...")
    logger.info("=" * 60)

    audio_manifest = synthesize_script(script, episode_dir)
    summary["audio_segments"] = len(audio_manifest)

    # === STEP 4: Assemble Audio ===
    logger.info("=" * 60)
    logger.info("STEP 4: Assembling episode audio...")
    logger.info("=" * 60)

    episode_audio = assemble_episode(audio_manifest, episode_dir, roster=roster)
    duration = get_episode_duration(episode_audio)
    summary["episode_audio"] = str(episode_audio)
    summary["duration_seconds"] = duration
    logger.info(f"Episode duration: {duration/60:.1f} minutes")

    # === STEP 5: Generate Video ===
    logger.info("=" * 60)
    logger.info("STEP 5: Generating video...")
    logger.info("=" * 60)

    episode_video = generate_landscape_video(
        audio_manifest, episode_audio, script, episode_dir
    )
    summary["episode_video"] = str(episode_video)

    # === STEP 6: Generate Clips ===
    logger.info("=" * 60)
    logger.info("STEP 6: Generating short-form clips...")
    logger.info("=" * 60)

    clip_segments = identify_clip_segments(script)
    clip_paths = extract_clips(clip_segments, audio_manifest, script, episode_dir)
    summary["clips"] = [str(p) for p in clip_paths]

    # === STEP 7: Distribute ===
    logger.info("=" * 60)
    logger.info("STEP 7: Distributing...")
    logger.info("=" * 60)

    # YouTube - full episode
    yt_episode_id = upload_episode(episode_video, script, date_str, roster=roster)
    yt_url = f"https://youtube.com/watch?v={yt_episode_id}" if yt_episode_id else None
    summary["youtube_episode_id"] = yt_episode_id

    # YouTube - clips
    yt_clip_ids = []
    for i, clip_path in enumerate(clip_paths):
        clip_title = (
            clip_segments[i]["title"] if i < len(clip_segments) else f"Clip {i+1}"
        )
        clip_id = upload_clip(clip_path, clip_title, yt_episode_id, roster=roster)
        if clip_id:
            yt_clip_ids.append(clip_id)
    summary["youtube_clip_ids"] = yt_clip_ids

    # Twitter/X - episode announcement
    tweet_id = post_episode_to_twitter(script, yt_url, roster=roster)
    summary["tweet_id"] = tweet_id

    # Twitter/X - clips
    for i, clip_path in enumerate(clip_paths):
        clip_title = (
            clip_segments[i]["title"] if i < len(clip_segments) else f"Clip {i+1}"
        )
        post_clip_to_twitter(clip_path, clip_title, yt_url, roster=roster)

    # RSS feed (append to existing)
    _update_rss_feed(script, episode_audio, duration, date_str)

    # === STEP 8: Cost Report ===
    cost_summary = tracker.save_report(episode_dir)
    summary["cost_usd"] = cost_summary["total_cost_usd"]

    # === Done ===
    summary["status"] = "complete"
    summary_path = episode_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info(f"Pipeline complete! Summary: {summary_path}")

    return summary


def _save_transcript(script: dict, episode_dir: Path, date_str: str):
    """Save a clean, readable transcript as a text file."""
    lines = []
    title = script.get("title", f"The AI Daily — {date_str}")
    lines.append(f"THE AI DAILY — {date_str}")
    lines.append(f'"{title}"')
    lines.append("=" * 60)
    lines.append("")

    for segment in script.get("segments", []):
        seg_type = segment.get("type", "").replace("_", " ").title()
        lines.append(f"--- {seg_type} ---")
        lines.append("")

        for dialogue in segment.get("dialogue", []):
            speaker = dialogue.get("speaker", "Unknown")
            text = dialogue.get("text", "")
            lines.append(f"  {speaker}: {text}")
            lines.append("")

    transcript_path = episode_dir / "transcript.txt"
    transcript_path.write_text("\n".join(lines), encoding="utf-8")


def _update_rss_feed(script: dict, audio_path: Path, duration: float, date_str: str):
    """Update the RSS feed with the new episode."""
    feed_data_path = config.OUTPUT_DIR / "feed_episodes.json"

    # Load existing episodes
    if feed_data_path.exists():
        episodes = json.loads(feed_data_path.read_text(encoding="utf-8"))
    else:
        episodes = []

    # Add new episode
    episodes.append(
        {
            "title": script.get("title", f"The AI Daily — {date_str}"),
            "description": script.get("description", ""),
            "date": date_str,
            "audio_url": "",  # Set this after hosting the MP3
            "duration_seconds": duration,
            "file_size_bytes": audio_path.stat().st_size,
        }
    )

    # Save updated list
    feed_data_path.write_text(json.dumps(episodes, indent=2), encoding="utf-8")

    # Regenerate feed
    # Convert date strings back to datetime for feedgen
    for ep in episodes:
        if isinstance(ep["date"], str):
            ep["date"] = datetime.strptime(ep["date"], "%Y-%m-%d")

    generate_feed(episodes, config.OUTPUT_DIR)


def run_scheduled():
    """Run the pipeline on a daily schedule."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BlockingScheduler()

    scheduler.add_job(
        run_pipeline,
        CronTrigger(
            hour=config.DAILY_RUN_HOUR,
            minute=0,
            timezone=config.TIMEZONE,
        ),
        id="daily_episode",
        name="Daily Episode Generation",
        misfire_grace_time=3600,
    )

    logger.info(
        f"Scheduler started. Episodes will generate daily at "
        f"{config.DAILY_RUN_HOUR}:00 {config.TIMEZONE}"
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="The AI Daily — Media Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="Run on a daily schedule instead of once",
    )
    parser.add_argument(
        "--script-only", action="store_true",
        help="Generate script only (no audio, video, or distribution)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Discover topics only (no generation)",
    )
    parser.add_argument(
        "--guest", type=str, default=None,
        help="Force a guest for this episode (e.g., --guest Gemini)",
    )
    parser.add_argument(
        "--roundtable", action="store_true",
        help="Force roundtable format with all speakers",
    )

    args = parser.parse_args()

    if args.schedule:
        run_scheduled()
    else:
        summary = run_pipeline(
            script_only=args.script_only,
            dry_run=args.dry_run,
            guest=args.guest,
            roundtable=args.roundtable,
        )

        if summary["status"] == "complete":
            logger.info("Episode published successfully!")
        elif summary["status"] in ("dry_run_complete", "script_complete"):
            logger.info(f"Partial run complete ({summary['status']})")
        else:
            logger.error(f"Pipeline failed: {summary.get('error', 'unknown')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
