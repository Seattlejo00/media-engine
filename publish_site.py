#!/usr/bin/env python3
"""
Publish an episode as a text article to the ai-daily-site repo.

Reads the episode artifacts produced by main.py (script.json, topics.json,
summary.json) and writes the website's article fragment + articles.json entry,
then runs the site's build script. Git commit/push is handled by the caller
(the GitHub Actions workflow).

Usage:
    python publish_site.py --episode-dir output/2026-07-11 --site-dir ../ai-daily-site
"""

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

# Speaker label colors, matching the site's established styling
# (see config.SPEAKERS "color" — these are the same values in hex).
SPEAKER_COLORS = {
    "Claude": "#cc7832",
    "ChatGPT": "#10a37f",
    "Gemini": "#4285f4",
    "Grok": "#ef4444",
}
DEFAULT_COLOR = "#8888a0"


def build_fragment(script: dict, topics: list[dict]) -> str:
    """Render the script as the site's article fragment HTML (body only)."""
    parts = []

    description = (script.get("description") or "").strip()
    if description:
        parts.append(f"<p>{html.escape(description)}</p>")
        parts.append("")

    for segment in script.get("segments", []):
        seg_type = segment.get("type", "")
        topic = (segment.get("topic") or "").strip()

        if seg_type == "sign_off":
            parts.append("<h2>Sign Off</h2>")
        elif seg_type in ("main_story", "lightning_round") and topic:
            parts.append(f"<h2>{html.escape(topic)}</h2>")

        for line in segment.get("dialogue", []):
            speaker = (line.get("speaker") or "").strip()
            text = html.escape((line.get("text") or "").strip())
            if not text:
                continue
            color = SPEAKER_COLORS.get(speaker, DEFAULT_COLOR)
            parts.append(
                f'<p><strong style="color:{color}">{html.escape(speaker)}:</strong> {text}</p>'
            )

    sources = [t for t in topics if t.get("url")]
    if sources:
        parts.append("")
        parts.append("<h3>Sources</h3>")
        parts.append("<ul>")
        for t in sources:
            title = html.escape((t.get("title") or "").strip())
            url = html.escape(t["url"])
            outlet = html.escape((t.get("source") or "").strip())
            suffix = f" ({outlet})" if outlet else ""
            parts.append(
                f'<li><a href="{url}" target="_blank" rel="noopener">{title}</a>{suffix}</li>'
            )
        parts.append("</ul>")

    return "\n".join(parts) + "\n"


def publish(episode_dir: Path, site_dir: Path) -> None:
    script = json.loads((episode_dir / "script.json").read_text(encoding="utf-8"))
    topics = json.loads((episode_dir / "topics.json").read_text(encoding="utf-8"))

    summary = {}
    summary_path = episode_dir / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    date_str = summary.get("date") or episode_dir.name

    yt_id = summary.get("youtube_episode_id")
    youtube_url = f"https://youtube.com/watch?v={yt_id}" if yt_id else None
    podcast_url = summary.get("podcast_audio_url") or None

    # 1. Article fragment
    fragment_path = site_dir / "static" / "articles" / f"{date_str}.html"
    fragment_path.parent.mkdir(parents=True, exist_ok=True)
    fragment_path.write_text(build_fragment(script, topics), encoding="utf-8")
    print(f"Wrote {fragment_path}")

    # 2. articles.json entry (insert new, or update existing entry for the date)
    articles_path = site_dir / "static" / "articles.json"
    episodes = json.loads(articles_path.read_text(encoding="utf-8"))

    entry = {
        "date": date_str,
        "title": script.get("title") or f"The AI Daily — {date_str}",
        "description": script.get("description") or "",
        "article_file": f"{date_str}.html",
        "youtube_url": youtube_url,
        "podcast_url": podcast_url,
        "roster": script.get("roster") or ["Claude", "ChatGPT"],
    }

    existing = next((e for e in episodes if e.get("date") == date_str), None)
    if existing:
        existing.update({k: v for k, v in entry.items() if v is not None})
        print(f"Updated existing articles.json entry for {date_str}")
    else:
        episodes.insert(0, entry)
        print(f"Added articles.json entry for {date_str}")

    episodes.sort(key=lambda e: e["date"], reverse=True)
    articles_path.write_text(
        json.dumps(episodes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # 3. Rebuild the site (episode pages, homepage list, RSS feed)
    build_script = site_dir / "scripts" / "build.py"
    if build_script.exists():
        subprocess.run([sys.executable, str(build_script)], check=True)
    else:
        print("WARNING: site has no scripts/build.py — skipping rebuild", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-dir", type=Path, required=True)
    parser.add_argument("--site-dir", type=Path, required=True)
    args = parser.parse_args()

    if not (args.episode_dir / "script.json").exists():
        sys.exit(f"No script.json in {args.episode_dir} — did main.py run?")
    if not (args.site_dir / "static" / "articles.json").exists():
        sys.exit(f"{args.site_dir} doesn't look like the ai-daily-site repo")

    publish(args.episode_dir, args.site_dir)


if __name__ == "__main__":
    main()
