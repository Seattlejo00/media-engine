"""
The Context Window — Media Engine
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
from pipeline.thumbnail import generate_thumbnail
from pipeline.cost_tracker import tracker
from distribution.youtube import upload_episode, upload_clip
from distribution.rss import generate_feed
from distribution.social import (
    post_episode_to_twitter, post_clip_to_twitter, upload_to_tiktok,
)
from distribution.podcast_host import upload_episode_audio

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


def _load_checkpoint(path: Path):
    """Load a JSON checkpoint file, or None if absent/corrupt."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Ignoring corrupt checkpoint {path.name}: {e}")
    return None


def run_pipeline(
    script_only: bool = False,
    dry_run: bool = False,
    guest: str | None = None,
    roundtable: bool = False,
    no_upload: bool = False,
    fresh: bool = False,
) -> dict:
    """
    Execute the full episode generation pipeline.

    Steps are checkpointed: any artifact already present in today's episode
    directory (topics.json, script.json, audio segments, video, clips) is
    reused instead of regenerated, so re-runs after a failure — or while
    testing — only pay for the stages that haven't completed yet.

    Returns a summary dict with paths and IDs.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    episode_dir = config.OUTPUT_DIR / date_str
    episode_dir.mkdir(parents=True, exist_ok=True)

    if fresh:
        # Wipe generated artifacts but KEEP the distribution ledger —
        # forgetting past uploads would cause duplicate YouTube posts.
        import shutil
        for item in episode_dir.iterdir():
            if item.name == "distribution_state.json":
                continue
            shutil.rmtree(item) if item.is_dir() else item.unlink()
        logger.info("--fresh: cleared today's artifacts (kept distribution_state.json)")

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

    topics_path = episode_dir / "topics.json"
    topics = _load_checkpoint(topics_path)
    if topics:
        logger.info("Reusing existing topics.json (use --fresh to regenerate)")
    else:
        topics = discover_topics()

        if not topics:
            logger.error("No topics found. Aborting.")
            summary["status"] = "failed"
            summary["error"] = "no_topics"
            return summary

        # Save topics
        topics_path.write_text(json.dumps(topics, indent=2), encoding="utf-8")
    summary["topics"] = [t["title"] for t in topics]
    logger.info(f"Topics: {[t['title'] for t in topics]}")

    if dry_run:
        logger.info("Dry run — stopping after topic discovery.")
        summary["status"] = "dry_run_complete"
        return summary

    # Daily "signal scores" for the website's scorecard (cheap, non-fatal)
    scores_path = episode_dir / "scores.json"
    if not scores_path.exists():
        scores = _generate_signal_scores(topics)
        if scores:
            scores_path.write_text(json.dumps(scores, indent=2), encoding="utf-8")

    # === STEP 1b: Research the stories ===
    logger.info("=" * 60)
    logger.info("STEP 1b: Researching stories (full articles)...")
    logger.info("=" * 60)

    research_path = episode_dir / "research.json"
    researched = _load_checkpoint(research_path)
    if researched:
        topics = researched
        logger.info("Reusing existing research.json")
    else:
        from pipeline.research import research_topics
        topics = research_topics(topics)
        research_path.write_text(
            json.dumps(topics, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # === STEP 2: Generate Script ===
    logger.info("=" * 60)
    logger.info("STEP 2: Generating script...")
    logger.info("=" * 60)

    script_path = episode_dir / "script.json"
    script = _load_checkpoint(script_path)
    if script:
        logger.info("Reusing existing script.json (use --fresh to regenerate)")
    else:
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

    manifest_path = episode_dir / "audio_manifest.json"
    audio_manifest = None
    cached_manifest = _load_checkpoint(manifest_path)
    if cached_manifest:
        restored = [{**m, "audio_path": Path(m["audio_path"])} for m in cached_manifest]
        if restored and all(m["audio_path"].exists() for m in restored):
            audio_manifest = restored
            logger.info(f"Reusing {len(restored)} synthesized audio segments")
    if audio_manifest is None:
        audio_manifest = synthesize_script(script, episode_dir)
        manifest_path.write_text(
            json.dumps(
                [{**m, "audio_path": str(m["audio_path"])} for m in audio_manifest],
                indent=2,
            ),
            encoding="utf-8",
        )
    summary["audio_segments"] = len(audio_manifest)

    # === STEP 4: Assemble Audio ===
    logger.info("=" * 60)
    logger.info("STEP 4: Assembling episode audio...")
    logger.info("=" * 60)

    episode_audio = episode_dir / "episode.mp3"
    if episode_audio.exists():
        logger.info("Reusing assembled episode.mp3")
    else:
        episode_audio = assemble_episode(audio_manifest, episode_dir, roster=roster)
    duration = get_episode_duration(episode_audio)
    summary["episode_audio"] = str(episode_audio)
    summary["duration_seconds"] = duration
    logger.info(f"Episode duration: {duration/60:.1f} minutes")

    # === STEP 5: Generate Video ===
    logger.info("=" * 60)
    logger.info("STEP 5: Generating video...")
    logger.info("=" * 60)

    episode_video = episode_dir / "episode_landscape.mp4"
    if episode_video.exists():
        logger.info("Reusing rendered episode_landscape.mp4")
    else:
        episode_video = generate_landscape_video(
            audio_manifest, episode_audio, script, episode_dir
        )
    summary["episode_video"] = str(episode_video)

    # --- Thumbnail ---
    thumbnail_path = episode_dir / "thumbnail.png"
    if thumbnail_path.exists():
        logger.info("Reusing existing thumbnail.png")
    else:
        logger.info("Generating thumbnail...")
        thumbnail_path = generate_thumbnail(script, topics, episode_dir, roster=roster)
    summary["thumbnail"] = str(thumbnail_path)

    # === STEP 6: Generate Clips ===
    logger.info("=" * 60)
    logger.info("STEP 6: Generating short-form clips...")
    logger.info("=" * 60)

    clip_segments_path = episode_dir / "clip_segments.json"
    clip_segments = _load_checkpoint(clip_segments_path)
    if clip_segments is None:
        clip_segments = identify_clip_segments(script)
        clip_segments_path.write_text(json.dumps(clip_segments, indent=2), encoding="utf-8")

    clips_dir = episode_dir / "clips"
    existing_clips = sorted(
        clips_dir.glob("clip_*.mp4"),
        key=lambda p: int(p.name.split("_")[1]),
    ) if clips_dir.exists() else []
    if clip_segments and len(existing_clips) >= len(clip_segments):
        clip_paths = existing_clips
        logger.info(f"Reusing {len(clip_paths)} rendered clips")
    else:
        clip_paths = extract_clips(clip_segments, audio_manifest, script, episode_dir)
    summary["clips"] = [str(p) for p in clip_paths]

    # === STEP 7: Distribute ===
    logger.info("=" * 60)
    logger.info("STEP 7: Distributing...")
    logger.info("=" * 60)

    if no_upload:
        logger.info("--no-upload: skipping all distribution (YouTube, X, TikTok, podcast)")
        summary["status"] = "complete_no_upload"
        cost_summary = tracker.save_report(episode_dir)
        summary["cost_usd"] = cost_summary["total_cost_usd"]
        summary_path = episode_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        logger.info(f"Pipeline complete (no uploads)! Summary: {summary_path}")
        return summary

    # The distribution ledger records every successful upload so a re-run
    # (after a crash, or while testing) never double-posts.
    ledger_path = episode_dir / "distribution_state.json"
    ledger = _load_checkpoint(ledger_path) or {}

    def _save_ledger():
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    # YouTube - full episode (with custom thumbnail)
    if ledger.get("youtube_episode_id"):
        yt_episode_id = ledger["youtube_episode_id"]
        logger.info(f"Episode already on YouTube ({yt_episode_id}) — skipping upload")
    else:
        yt_episode_id = upload_episode(
            episode_video, script, date_str, roster=roster, thumbnail_path=thumbnail_path,
        )
        if yt_episode_id:
            ledger["youtube_episode_id"] = yt_episode_id
            _save_ledger()
    yt_url = f"https://youtube.com/watch?v={yt_episode_id}" if yt_episode_id else None
    summary["youtube_episode_id"] = yt_episode_id

    # YouTube - clips (capped to avoid daily upload limit)
    max_yt_clips = config.MAX_CLIPS_UPLOAD
    yt_clip_ids = ledger.setdefault("youtube_clip_ids", {})
    for i, clip_path in enumerate(clip_paths[:max_yt_clips]):
        if str(i) in yt_clip_ids:
            continue
        clip_title = (
            clip_segments[i]["title"] if i < len(clip_segments) else f"Clip {i+1}"
        )
        clip_id = upload_clip(clip_path, clip_title, yt_episode_id, roster=roster)
        if clip_id:
            yt_clip_ids[str(i)] = clip_id
            _save_ledger()
    if len(clip_paths) > max_yt_clips:
        logger.info(
            f"Uploaded {max_yt_clips}/{len(clip_paths)} clips to YouTube "
            f"(MAX_CLIPS_UPLOAD={max_yt_clips})"
        )
    summary["youtube_clip_ids"] = list(yt_clip_ids.values())

    # Twitter/X - episode announcement
    if ledger.get("tweet_id"):
        tweet_id = ledger["tweet_id"]
    else:
        tweet_id = post_episode_to_twitter(script, yt_url, roster=roster)
        if tweet_id:
            ledger["tweet_id"] = tweet_id
            _save_ledger()
    summary["tweet_id"] = tweet_id

    # Twitter/X - clips
    if not ledger.get("twitter_clips_posted"):
        for i, clip_path in enumerate(clip_paths):
            clip_title = (
                clip_segments[i]["title"] if i < len(clip_segments) else f"Clip {i+1}"
            )
            post_clip_to_twitter(clip_path, clip_title, yt_url, roster=roster)
        ledger["twitter_clips_posted"] = True
        _save_ledger()

    # TikTok - clips
    tiktok_ids = ledger.setdefault("tiktok_ids", {})
    for i, clip_path in enumerate(clip_paths):
        if str(i) in tiktok_ids:
            continue
        clip_title = (
            clip_segments[i]["title"] if i < len(clip_segments) else f"Clip {i+1}"
        )
        hashtags = " ".join(f"#{name}" for name in roster)
        tiktok_title = f"{clip_title} | The Context Window {hashtags} #AI #Podcast"
        tiktok_id = upload_to_tiktok(clip_path, tiktok_title)
        if tiktok_id:
            tiktok_ids[str(i)] = tiktok_id
            _save_ledger()
    summary["tiktok_ids"] = list(tiktok_ids.values())

    # Instagram - Reels (video is fetched from R2, so R2 must be configured)
    from distribution.instagram import (
        instagram_configured, post_reel, refresh_access_token,
    )
    from distribution.podcast_host import upload_social_clip

    ig_ids = ledger.setdefault("instagram_ids", {})
    if instagram_configured():
        refresh_access_token()
        for i, clip_path in enumerate(clip_paths[:config.INSTAGRAM_MAX_CLIPS]):
            if str(i) in ig_ids:
                continue
            clip_title = (
                clip_segments[i]["title"] if i < len(clip_segments) else f"Clip {i+1}"
            )
            video_url = upload_social_clip(clip_path, date_str, i)
            if not video_url:
                logger.warning("No public URL for clip (R2 unconfigured?) — skipping Instagram")
                break
            caption = (
                f"{clip_title}\n\nFrom today's episode of The Context Window — "
                f"the daily AI news podcast hosted by AIs.\n\n"
                f"#AI #ArtificialIntelligence #TechNews #Podcast #Reels"
            )
            media_id = post_reel(video_url, caption)
            if media_id:
                ig_ids[str(i)] = media_id
                _save_ledger()
    summary["instagram_ids"] = list(ig_ids.values())

    # Podcast hosting — upload MP3 for Spotify/Apple
    if ledger.get("podcast_audio_url"):
        audio_url = ledger["podcast_audio_url"]
    else:
        audio_url = upload_episode_audio(episode_audio, date_str)
        if audio_url:
            ledger["podcast_audio_url"] = audio_url
            _save_ledger()
    summary["podcast_audio_url"] = audio_url

    # RSS feed (append to existing; same-day re-runs replace the entry)
    _update_rss_feed(script, episode_audio, duration, date_str, audio_url=audio_url)

    # === STEP 8: Cost Report ===
    cost_summary = tracker.save_report(episode_dir)
    summary["cost_usd"] = cost_summary["total_cost_usd"]

    # === Done ===
    summary["status"] = "complete"
    summary_path = episode_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info(f"Pipeline complete! Summary: {summary_path}")

    return summary


def _generate_signal_scores(topics: list[dict]) -> dict | None:
    """
    Score today's news signal per category (0-10) for the website scorecard.

    Returns e.g. {"overall": 8.7, "label": "High signal day",
                  "categories": {"Models": 9.1, "Research": 7.2, ...}}
    """
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        headlines = "\n".join(
            f"- [{t.get('category', 'news')}] {t['title']}: {t.get('description', '')[:150]}"
            for t in topics
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=300,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You rate the significance of a day's AI news for a "
                        "podcast scorecard. Score 0-10 by impact, novelty and "
                        "reach. Be discriminating: most days are 5-7, reserve "
                        "9+ for landmark news. Return ONLY JSON: "
                        '{"overall": float, "label": "<2-4 word day summary>", '
                        '"categories": {"Models": float, "Research": float, '
                        '"Industry": float, "Startups": float}}'
                    ),
                },
                {"role": "user", "content": f"Today's stories:\n{headlines}"},
            ],
        )
        scores = json.loads(resp.choices[0].message.content)
        tracker.record(
            step="signal_scores", model="gpt-4o-mini",
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
        )
        logger.info(f"Signal scores: {scores}")
        return scores
    except Exception as e:
        logger.warning(f"Signal score generation failed (non-fatal): {e}")
        return None


def _save_transcript(script: dict, episode_dir: Path, date_str: str):
    """Save a clean, readable transcript as a text file."""
    lines = []
    title = script.get("title", f"The Context Window — {date_str}")
    lines.append(f"THE CONTEXT WINDOW — {date_str}")
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


def _update_rss_feed(
    script: dict, audio_path: Path, duration: float, date_str: str,
    audio_url: str | None = None,
):
    """Update the RSS feed with the new episode."""
    feed_data_path = config.OUTPUT_DIR / "feed_episodes.json"

    # CI runners have no local history — R2 is the source of truth
    if not feed_data_path.exists():
        from distribution.podcast_host import download_feed_state
        download_feed_state(feed_data_path)

    # Load existing episodes
    if feed_data_path.exists():
        episodes = json.loads(feed_data_path.read_text(encoding="utf-8"))
    else:
        episodes = []

    # Don't duplicate an episode if the pipeline re-runs for the same day
    episodes = [ep for ep in episodes if ep.get("date") != date_str]

    # Add new episode
    episodes.append(
        {
            "title": script.get("title", f"The Context Window — {date_str}"),
            "description": script.get("description", ""),
            "date": date_str,
            "audio_url": audio_url or "",
            "duration_seconds": duration,
            "file_size_bytes": audio_path.stat().st_size,
        }
    )

    # Save updated list
    feed_data_path.write_text(json.dumps(episodes, indent=2), encoding="utf-8")

    # Without a feed URL (i.e. R2 hosting unconfigured) feedgen has no
    # required <link> and the feed would have no audio anyway — skip.
    if not config.RSS_FEED_URL:
        logger.warning("RSS_FEED_URL / R2 not configured — skipping podcast feed generation")
        return

    # Regenerate feed
    # Convert date strings back to datetime for feedgen
    for ep in episodes:
        if isinstance(ep["date"], str):
            ep["date"] = datetime.strptime(ep["date"], "%Y-%m-%d")

    feed_path = generate_feed(episodes, config.OUTPUT_DIR)

    # Publish feed.xml + episode history to R2 so Spotify/Apple can poll it
    from distribution.podcast_host import upload_feed
    upload_feed(feed_path, feed_data_path)


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
        description="The Context Window — Media Engine",
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
    parser.add_argument(
        "--no-upload", action="store_true",
        help="Generate everything but skip all distribution (YouTube, X, "
             "TikTok, podcast) — safe for testing",
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Regenerate today's artifacts from scratch instead of reusing "
             "checkpoints (the upload ledger is preserved)",
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
            no_upload=args.no_upload,
            fresh=args.fresh,
        )

        if summary["status"] == "complete":
            logger.info("Episode published successfully!")
        elif summary["status"] in ("dry_run_complete", "script_complete", "complete_no_upload"):
            logger.info(f"Partial run complete ({summary['status']})")
        else:
            logger.error(f"Pipeline failed: {summary.get('error', 'unknown')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
