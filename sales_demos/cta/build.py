"""Build the private Colorado Tech Signal sales concept without publishing."""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import imageio_ffmpeg


ROOT = Path(__file__).resolve().parents[2]
DATE = datetime.now().strftime("%Y-%m-%d")
OUTPUT_ROOT = ROOT / "output" / "cta-concept" / DATE
OUTPUT_DIR = OUTPUT_ROOT / "single-anchor"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
sys.path.insert(0, str(ROOT))

# MoviePy reads this before importing its ffmpeg integration. The waveform
# overlay reads FFMPEG_BIN directly.
os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG
os.environ["FFMPEG_BIN"] = FFMPEG

import config  # noqa: E402


def configure_concept(*, premium_voice: bool = False) -> list[str]:
    """Apply an in-memory publication profile; production defaults stay intact."""
    config.OUTPUT_DIR = ROOT / "output" / "cta-concept"
    config.PODCAST_TITLE = "Colorado Tech Signal"
    config.PUBLICATION_FORMAT = "weekly Colorado technology intelligence briefing"
    config.PUBLICATION_AUDIENCE = (
        "Colorado technology executives, operators, founders, and policy leaders"
    )
    config.PODCAST_DESCRIPTION = (
        "A concise briefing on the Colorado technology stories shaping business, "
        "policy, infrastructure, and the state's innovation economy."
    )
    config.PODCAST_THUMBNAIL_LABEL = "COLORADO TECHNOLOGY  •  PRIVATE CONCEPT"
    config.PODCAST_TAGLINE = "COLORADO TECHNOLOGY, IN CONTEXT"
    config.PODCAST_CADENCE = "A weekly member intelligence concept"
    config.PODCAST_SITE_LABEL = "PROPOSED WEEKLY MEMBER BRIEFING"
    config.PODCAST_STORY_EYEBROW = "MEMBER SIGNAL"
    config.PODCAST_PRIMARY_CTA = "PRIVATE CONCEPT  •  DISTOMOS"
    config.PODCAST_SECONDARY_CTA = "PROPOSED FOR WEEKLY MEMBER BRIEFINGS"
    config.PODCAST_CLIP_CTA_HEADLINE = "PRIVATE CONCEPT"
    config.PODCAST_CLIP_CTA_DETAIL = "BY DISTOMOS"
    config.PODCAST_CLIP_CTA_DESTINATION = "PROPOSED FOR CTA"
    config.PODCAST_YOUTUBE_CLIP_CTA_HEADLINE = "PRIVATE CONCEPT"
    config.PODCAST_YOUTUBE_CLIP_CTA_DETAIL = "BY DISTOMOS"
    config.PODCAST_YOUTUBE_CLIP_CTA_DESTINATION = "NOT FOR PUBLICATION"

    config.SPEAKERS["Mara"] = {
        "company": "Colorado technology briefing",
        "voice": "marin" if premium_voice else "Moira",
        "voice_instructions": "Warm, reassuring, and unhurried.",
        "tts_speed": 1.0,
        "color": (76, 145, 255),
        "model": "local-editorial-concept",
        "api_type": "local",
        "persona_prompt": "",
        "role": "host",
    }
    return ["Mara"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--premium-segments-dir",
        type=Path,
        help="Directory containing premium TTS files named 000.mp3, 001.mp3, and so on.",
    )
    parser.add_argument(
        "--output-variant",
        default="single-anchor",
        help="Subdirectory under the dated CTA concept output.",
    )
    return parser.parse_args()


SOURCES = [
    {
        "title": "Space Development Agency awards Sierra Space up to $798 million",
        "publisher": "U.S. Space Development Agency",
        "url": (
            "https://www.sda.mil/space-development-agency-issues-awards-to-build-"
            "36-accelerated-missile-defense-tracking-layer-satellites-for-tranche-"
            "3-in-support-of-golden-dome-for-america/"
        ),
    },
    {
        "title": "The Thirst for Data: state responses to data-center water demand",
        "publisher": "University of Colorado Boulder / Newswise",
        "url": (
            "https://www.newswise.com/articles/the-thirst-for-data-new-report-examines-"
            "state-responses-to-data-center-water-demand"
        ),
    },
    {
        "title": "Zayo announces planned CEO transition",
        "publisher": "Zayo",
        "url": (
            "https://www.zayo.com/newsroom/zayo-announces-planned-ceo-transition-"
            "as-company-enters-next-phase-of-ai-driven-digital-infrastructure-growth/"
        ),
    },
]


TOPICS = [
    {
        "rank": 1,
        "category": "main",
        "title": "Sierra Space wins a potential $798 million missile-tracking satellite award",
        "summary": (
            "The Space Development Agency selected Louisville-based Sierra Space "
            "to provide 18 missile-warning and tracking satellites."
        ),
        "source": "U.S. Space Development Agency",
        "url": SOURCES[0]["url"],
        "signal": "$798M potential value · 18 satellites · 2028 target",
        "member_takeaway": (
            "Track Colorado hiring, supplier awards, and delivery milestones to see "
            "whether the contract compounds across the regional space economy."
        ),
        "brief": {
            "key_facts": [
                "SDA announced two agreements worth approximately $1.75 billion in total.",
                "Sierra Space's agreement has a total potential value of $798 million.",
                "Sierra Space is to provide 18 missile-warning and tracking satellites across two orbital planes.",
                "The satellites are expected to be available for launch by the end of 2028.",
                "The satellites will use infrared sensing payloads in low Earth orbit and connect to a low-latency communications network.",
            ],
            "sources": ["U.S. Space Development Agency"],
        },
    },
    {
        "rank": 2,
        "category": "main",
        "title": "CU Boulder maps the emerging fight over data-center water use",
        "summary": (
            "A CU Law report identifies four policy approaches states are using "
            "or considering as AI and cloud infrastructure increase water demand."
        ),
        "source": "University of Colorado Boulder / Newswise",
        "url": SOURCES[1]["url"],
        "signal": "4 policy routes · reporting comes first",
        "member_takeaway": (
            "Treat water disclosure, cooling design, utility planning, and community "
            "engagement as one AI-infrastructure strategy."
        ),
        "brief": {
            "key_facts": [
                "The report synthesizes state legislative activity through June 2026.",
                "It identifies reporting, conservation, incentives, and prior-appropriation requirements as four policy approaches.",
                "A significant share of data-center expansion is occurring in the water-constrained western United States.",
                "The report says the policy landscape is early and emphasizes better water-use data and public reporting.",
            ],
            "sources": ["University of Colorado Boulder / Newswise"],
        },
    },
    {
        "rank": 3,
        "category": "lightning",
        "title": "Denver-based Zayo chooses a former Verizon executive for its AI infrastructure chapter",
        "summary": (
            "Zayo appointed Sowmyanarayan Sampath as CEO effective September 1, "
            "framing the transition around rising demand for AI connectivity."
        ),
        "source": "Zayo",
        "url": SOURCES[2]["url"],
        "signal": "15,000+ route miles of announced expansion",
        "member_takeaway": (
            "AI connectivity is shifting from a construction race toward commercial "
            "execution, reliability, and durable enterprise relationships."
        ),
        "brief": {
            "key_facts": [
                "Sowmyanarayan Sampath becomes CEO on September 1, 2026.",
                "He previously led Verizon Consumer and Verizon Business.",
                "Zayo says its recent expansion projects span more than 15,000 route miles.",
                "Its Crown Castle fiber acquisition added about 90,000 route miles and 40,000 on-net enterprise locations.",
            ],
            "sources": ["Zayo"],
        },
    },
]


SCRIPT = {
    "title": "Colorado's $798M Space Win Meets AI's Water Reality",
    "youtube_title": "Colorado's $798M Space Win—and AI's Water Bill",
    "description": (
        "Sierra Space lands a major federal satellite award, CU Boulder maps the "
        "water-policy choices surrounding AI infrastructure, and Zayo names the "
        "leader for its next phase of connectivity growth."
    ),
    "roster": ["Mara"],
    "segments": [
        {
            "type": "cold_open",
            "topic": TOPICS[0]["title"],
            "dialogue": [
                {
                    "speaker": "Mara",
                    "text": (
                        "A Louisville company has secured a potential seven-hundred-"
                        "ninety-eight-million-dollar role in America's next missile-"
                        "tracking network. At the same time, Colorado researchers are "
                        "mapping a constraint beneath the AI boom: water. Together, those "
                        "stories show where Colorado technology is gaining leverage—and "
                        "where growth could meet resistance."
                    ),
                },
            ],
        },
        {
            "type": "intro",
            "topic": None,
            "dialogue": [
                {
                    "speaker": "Mara",
                    "text": (
                        "This is Colorado Tech Signal for July eighteenth, twenty "
                        "twenty-six—a private Distomos concept for a source-linked weekly "
                        "member briefing. Today: Sierra Space, data-center water policy, "
                        "and Zayo's next AI-infrastructure chapter."
                    ),
                },
            ],
        },
        {
            "type": "main_story",
            "topic": TOPICS[0]["title"],
            "dialogue": [
                {
                    "speaker": "Mara",
                    "text": (
                        "The U.S. Space Development Agency awarded Sierra Space an agreement "
                        "with a potential value of seven-hundred-ninety-eight million dollars. "
                        "The Louisville company is to provide eighteen missile-warning and "
                        "tracking satellites across two orbital planes, available for launch "
                        "by the end of twenty twenty-eight."
                    ),
                },
                {
                    "speaker": "Mara",
                    "text": (
                        "For Colorado technology leaders, the durable opportunity is the "
                        "supply chain around the award: advanced manufacturing, optics, "
                        "software, systems integration, testing, and specialized talent. "
                        "The contract establishes scale; hiring and supplier activity will "
                        "show how widely that scale compounds across the state."
                    ),
                },
                {
                    "speaker": "Mara",
                    "text": (
                        "The member watch item is execution. Track Colorado job openings, "
                        "local supplier announcements, and progress against the twenty-"
                        "twenty-eight launch target. Those indicators will separate a large "
                        "headline from a broader regional growth story."
                    ),
                },
            ],
        },
        {
            "type": "main_story",
            "topic": TOPICS[1]["title"],
            "dialogue": [
                {
                    "speaker": "Mara",
                    "text": (
                        "Colorado Law's Getches-Wilkinson Center has published Thirst for "
                        "Data, a review of state policy responses to data-center water "
                        "demand. It identifies four routes: reporting, conservation rules, "
                        "incentives for low-water technology, and requirements tied to "
                        "existing water rights and availability."
                    ),
                },
                {
                    "speaker": "Mara",
                    "text": (
                        "The useful shift is from a vague fight over whether data centers "
                        "use too much water to decisions companies can plan around. What "
                        "must be disclosed? Which efficiencies earn incentives? What water "
                        "is legally available? Without comparable local data, communities "
                        "cannot reward good engineering and operators cannot prove improvement."
                    ),
                },
                {
                    "speaker": "Mara",
                    "text": (
                        "The member action is to treat water policy as AI infrastructure "
                        "strategy now. Site selection, utility planning, cooling design, "
                        "and community relations already meet in the same boardroom. Companies "
                        "that document performance and engage before rules are final will be "
                        "better positioned than those reacting after the fact."
                    ),
                },
            ],
        },
        {
            "type": "lightning_round",
            "topic": TOPICS[2]["title"],
            "dialogue": [
                {
                    "speaker": "Mara",
                    "text": (
                        "One more infrastructure signal: Denver-based Zayo appointed former "
                        "Verizon executive Sowmyanarayan Sampath as chief executive, effective "
                        "September first. Zayo framed the transition around AI and enterprise "
                        "growth after expansion projects covering more than fifteen-thousand "
                        "route miles."
                    ),
                },
                {
                    "speaker": "Mara",
                    "text": (
                        "For members, the signal is that AI infrastructure is becoming a "
                        "commercial execution race, not only a construction race. Dense "
                        "computing needs fiber, but capacity creates value only when operators "
                        "turn it into resilient services and durable customer relationships."
                    ),
                },
                {
                    "speaker": "Mara",
                    "text": (
                        "Put the three stories together and the pattern is physical: satellites, "
                        "water, and fiber. Colorado's advanced-technology opportunity—and its "
                        "constraints—are being built in hardware, utilities, talent, and networks."
                    ),
                },
            ],
        },
        {
            "type": "sign_off",
            "topic": None,
            "dialogue": [
                {
                    "speaker": "Mara",
                    "text": (
                        "This week's watch list: Sierra Space hiring and supplier activity, "
                        "movement toward verified data-center water reporting, and how Zayo "
                        "translates network scale into enterprise growth. The sources and a "
                        "written summary accompany this briefing."
                    ),
                },
                {
                    "speaker": "Mara",
                    "text": (
                        "That's Colorado Tech Signal. Thank you for listening."
                    ),
                },
            ],
        },
    ],
}


def synthesize_local(script: dict, roster: list[str]) -> list[dict]:
    """Generate per-turn MP3s with built-in macOS voices."""
    from pydub import AudioSegment

    AudioSegment.converter = FFMPEG
    audio_dir = OUTPUT_DIR / "audio_segments"
    audio_dir.mkdir(parents=True, exist_ok=True)
    voice_by_speaker = {"Mara": ("Moira", 155)}
    manifest = []
    index = 0

    for segment in script["segments"]:
        for line in segment["dialogue"]:
            speaker = line["speaker"]
            voice, rate = voice_by_speaker[speaker]
            voice_slug = voice.lower().replace(" ", "-")
            stem = f"{index:03d}_{speaker.lower()}_{voice_slug}_{rate}_{segment['type']}"
            aiff_path = audio_dir / f"{stem}.aiff"
            mp3_path = audio_dir / f"{stem}.mp3"
            if not mp3_path.exists():
                subprocess.run(
                    [
                        "say", "-v", voice, "-r", str(rate),
                        "-o", str(aiff_path), line["text"],
                    ],
                    check=True,
                )
                subprocess.run(
                    [
                        FFMPEG, "-y", "-loglevel", "error", "-i", str(aiff_path),
                        "-codec:a", "libmp3lame", "-b:a", "160k", str(mp3_path),
                    ],
                    check=True,
                )
                aiff_path.unlink(missing_ok=True)
            manifest.append(
                {
                    "speaker": speaker,
                    "text": line["text"],
                    "audio_path": mp3_path,
                    "segment_type": segment["type"],
                    "topic": segment.get("topic"),
                    "index": index,
                }
            )
            index += 1

    (OUTPUT_DIR / "audio_manifest.json").write_text(
        json.dumps(
            [{**entry, "audio_path": str(entry["audio_path"])} for entry in manifest],
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def synthesize_from_directory(script: dict, source_dir: Path) -> list[dict]:
    """Build a manifest from externally generated, per-turn premium TTS files."""
    manifest = []
    index = 0
    for segment in script["segments"]:
        for line in segment["dialogue"]:
            audio_path = source_dir / f"{index:03d}.mp3"
            if not audio_path.is_file():
                raise FileNotFoundError(f"Missing premium TTS turn {index}: {audio_path}")
            manifest.append(
                {
                    "speaker": line["speaker"],
                    "text": line["text"],
                    "audio_path": audio_path,
                    "segment_type": segment["type"],
                    "topic": segment.get("topic"),
                    "index": index,
                }
            )
            index += 1

    (OUTPUT_DIR / "audio_manifest.json").write_text(
        json.dumps(
            [{**entry, "audio_path": str(entry["audio_path"])} for entry in manifest],
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def write_editorial_files(*, premium_voice: bool = False) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "topics.json").write_text(
        json.dumps(TOPICS, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUTPUT_DIR / "research.json").write_text(
        json.dumps(TOPICS, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUTPUT_DIR / "script.json").write_text(
        json.dumps(SCRIPT, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    transcript = [f"# {config.PODCAST_TITLE}", "", f"{DATE} · Private concept", ""]
    if premium_voice:
        transcript.extend(
            [
                "**AI voice disclosure:** The anchor voice is generated by artificial "
                "intelligence and is not a recording of a human speaker.",
                "",
            ]
        )
    for segment in SCRIPT["segments"]:
        transcript.extend([f"## {segment['type'].replace('_', ' ').title()}", ""])
        for line in segment["dialogue"]:
            transcript.extend([f"**{line['speaker']}:** {line['text']}", ""])
    (OUTPUT_DIR / "transcript.md").write_text("\n".join(transcript), encoding="utf-8")

    source_lines = ["# Sources", ""]
    for source in SOURCES:
        source_lines.append(
            f"- [{source['publisher']}: {source['title']}]({source['url']})"
        )
    (OUTPUT_DIR / "sources.md").write_text("\n".join(source_lines), encoding="utf-8")

    voice_disclosure = (
        "\n**AI voice disclosure:** The anchor voice is generated by artificial "
        "intelligence and is not a recording of a human speaker.\n"
        if premium_voice
        else ""
    )
    email_summary = f"""# Email-ready member summary

## Colorado's $798M space win meets AI's water reality
{voice_disclosure}

This week's three signals:

- **Space:** Louisville-based Sierra Space received a federal agreement with a potential value of $798 million to provide 18 missile-warning and tracking satellites.
- **Infrastructure:** A new CU Boulder report organizes state responses to data-center water use into four approaches: reporting, conservation, incentives, and prior-appropriation requirements.
- **Networks:** Denver-based Zayo appointed former Verizon executive Sowmyanarayan Sampath as CEO as it positions for AI-driven connectivity demand.

Listen to the private concept episode or review the source-linked transcript.

*Unofficial concept by Distomos. Not produced by or endorsed by CTA.*
"""
    (OUTPUT_DIR / "email_summary.md").write_text(email_summary, encoding="utf-8")


def write_demo_page(
    duration_seconds: float,
    clip_paths: dict[str, list[Path]],
    *,
    premium_voice: bool = False,
) -> None:
    transcript_html = []
    for segment in SCRIPT["segments"]:
        transcript_html.append(
            f"<h3>{html.escape(segment['type'].replace('_', ' ').title())}</h3>"
        )
        for line in segment["dialogue"]:
            transcript_html.append(
                f"<p><strong>{html.escape(line['speaker'])}:</strong> "
                f"{html.escape(line['text'])}</p>"
            )
    sources_html = "".join(
        f'<li><a href="{html.escape(source["url"])}" target="_blank" rel="noopener">'
        f'{html.escape(source["publisher"])} — {html.escape(source["title"])}</a></li>'
        for source in SOURCES
    )
    social_clip = (
        clip_paths.get("social", [None])[0].relative_to(OUTPUT_DIR)
        if clip_paths.get("social") else None
    )
    clip_html = (
        f'<video controls preload="metadata" src="{html.escape(str(social_clip))}"></video>'
        if social_clip else "<p>Clip render unavailable.</p>"
    )
    story_cards_html = "".join(
        "<article class=\"signal\">"
        f"<p class=\"kicker\">SIGNAL {topic['rank']}</p>"
        f"<h3>{html.escape(topic['title'])}</h3>"
        f"<p class=\"metric\">{html.escape(topic['signal'])}</p>"
        f"<p><strong>Member takeaway:</strong> {html.escape(topic['member_takeaway'])}</p>"
        "</article>"
        for topic in TOPICS
    )
    voice_disclosure = (
        '<div class="notice"><strong>AI voice disclosure:</strong> The anchor voice '
        "in this episode is generated by artificial intelligence and is not a recording "
        "of a human speaker.</div>"
        if premium_voice
        else ""
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Colorado Tech Signal — private concept</title>
<style>
:root{{--ink:#eef2ff;--muted:#aeb8d3;--bg:#080b16;--panel:#12182a;--blue:#4c91ff;--orange:#f4a64d}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 20% 0,#15264a 0,transparent 38%),var(--bg);color:var(--ink);font:16px/1.65 system-ui,sans-serif}}
main{{width:min(1080px,calc(100% - 32px));margin:auto;padding:48px 0 90px}}.notice{{border:1px solid #7b6738;background:#221d12;color:#f4d999;padding:12px 16px;border-radius:10px}}
h1{{font-size:clamp(42px,8vw,88px);line-height:.9;letter-spacing:-.055em;margin:70px 0 24px}}h1 em{{color:var(--blue);font-style:normal}}.dek{{color:var(--muted);font-size:20px;max-width:720px}}
.grid{{display:grid;grid-template-columns:1.7fr .7fr;gap:24px;margin:44px 0}}.card{{background:rgba(18,24,42,.86);border:1px solid #28324d;border-radius:18px;padding:24px}}
.signals{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}.signal{{background:linear-gradient(155deg,#151d33,#0d1222);border:1px solid #2c3858;border-radius:16px;padding:22px}}.signal h3{{color:var(--ink);font-size:20px;line-height:1.25;margin:10px 0}}.kicker{{color:var(--blue);font-weight:800;letter-spacing:.12em;font-size:12px}}.metric{{color:#f4d999;font-weight:700}}
audio,video{{width:100%}}video{{max-height:620px;background:#05070d;border-radius:12px}}h2{{font-size:30px;margin-top:64px}}h3{{color:var(--orange);margin-top:38px}}
a{{color:#84b4ff}}p{{max-width:800px}}small{{color:var(--muted)}}@media(max-width:760px){{.grid,.signals{{grid-template-columns:1fr}}}}
</style></head><body><main>
<div class="notice"><strong>Private, unofficial concept.</strong> Not produced by or endorsed by the Colorado Technology Association. Do not publish.</div>
{voice_disclosure}
<h1>Colorado<br><em>Tech Signal</em></h1>
<p class="dek">A source-transparent weekly briefing concept for Colorado technology leaders—one research cycle, delivered as audio, video, clips, transcript, and email-ready copy.</p>
<div class="grid"><section class="card"><h2>Concept episode</h2><p>{html.escape(SCRIPT['title'])} · {duration_seconds/60:.1f} minutes</p><audio controls preload="metadata" src="episode.mp3"></audio><p><a href="episode_landscape.mp4">Open full video</a> · <a href="transcript.md">Transcript</a> · <a href="email_summary.md">Email summary</a></p></section><aside class="card"><h2>Short-form cut</h2>{clip_html}</aside></div>
<h2>Three signals, three member actions</h2><section class="signals">{story_cards_html}</section>
<h2>Transcript</h2>{''.join(transcript_html)}
<h2>Sources</h2><ul>{sources_html}</ul>
<p><small>Concept built by Distomos on {DATE}. Editorial analysis is clearly distinguished from source-reported facts.</small></p>
</main></body></html>"""
    (OUTPUT_DIR / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    global OUTPUT_DIR
    args = parse_args()
    premium_voice = args.premium_segments_dir is not None
    OUTPUT_DIR = OUTPUT_ROOT / args.output_variant
    roster = configure_concept(premium_voice=premium_voice)
    write_editorial_files(premium_voice=premium_voice)

    from pydub import AudioSegment
    from pipeline.audio import assemble_episode, get_episode_duration
    from pipeline.clips import extract_clips
    from pipeline.thumbnail import generate_thumbnail
    from pipeline.video import generate_landscape_video

    AudioSegment.converter = FFMPEG
    if args.premium_segments_dir:
        manifest = synthesize_from_directory(SCRIPT, args.premium_segments_dir)
    else:
        manifest = synthesize_local(SCRIPT, roster)
    episode_audio = assemble_episode(manifest, OUTPUT_DIR, roster=roster)
    duration = get_episode_duration(episode_audio)
    generate_landscape_video(manifest, episode_audio, SCRIPT, OUTPUT_DIR)
    generate_thumbnail(SCRIPT, TOPICS, OUTPUT_DIR, roster=roster)

    clip_segments = [
        {
            "start_index": 7,
            "end_index": 7,
            "title": "The AI water-policy advantage",
            "on_screen_hook": "ACT BEFORE THE RULES ARE FINAL",
        }
    ]
    (OUTPUT_DIR / "clip_segments.json").write_text(
        json.dumps(clip_segments, indent=2), encoding="utf-8"
    )
    clips = extract_clips(clip_segments, manifest, SCRIPT, OUTPUT_DIR)
    write_demo_page(duration, clips, premium_voice=premium_voice)

    summary = {
        "status": "complete_no_upload",
        "date": DATE,
        "publication": config.PODCAST_TITLE,
        "format": "single_anchor_member_briefing",
        "tts_status": (
            "premium_marin_selected"
            if premium_voice
            else "local_placeholder_pending_premium_voice_audition"
        ),
        "duration_seconds": duration,
        "episode_audio": str(episode_audio),
        "episode_video": str(OUTPUT_DIR / "episode_landscape.mp4"),
        "thumbnail": str(OUTPUT_DIR / "thumbnail.png"),
        "clips": {key: [str(path) for path in paths] for key, paths in clips.items()},
        "demo_page": str(OUTPUT_DIR / "index.html"),
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
