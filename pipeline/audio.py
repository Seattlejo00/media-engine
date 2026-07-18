"""
Audio assembly.
Stitches individual TTS segments into a full episode MP3 with the show's
sonic logo (intro/stinger/outro), natural pauses, and normalized volume.
Also emits chapter timings for YouTube.
"""

import json
import logging
from pathlib import Path

from pydub import AudioSegment
from pydub.effects import normalize

import config

logger = logging.getLogger(__name__)

# Timing constants (milliseconds)
PAUSE_BETWEEN_LINES = 400        # Natural breath pause between speakers
PAUSE_WITHIN_SPEAKER = 200       # Shorter pause when same speaker continues
STINGER_PAD = 700                # Silence on each side of a segment stinger
                                 # (also sets how long UP NEXT cards hold)
PAUSE_AFTER_INTRO = 600          # Between the intro sting and the first line
PAUSE_BEFORE_OUTRO = 500         # Between the last line and the outro sting
OUTRO_SILENCE = 1200             # Silence at the very end

ASSETS_DIR = config.BASE_DIR / "assets"
STINGER_GAIN_DB = -6  # keep the sonic logo under the voice level


def _load_sting(name: str) -> AudioSegment | None:
    """Load a sonic-logo asset; None if missing (assembly degrades to silence)."""
    path = ASSETS_DIR / name
    if not path.exists():
        logger.warning(f"Missing audio asset {path} — using silence instead")
        return None
    return AudioSegment.from_file(str(path)).apply_gain(STINGER_GAIN_DB)


def sting_durations_ms() -> dict[str, int]:
    """Durations of the sonic-logo pieces — the video mirrors these exactly."""
    out = {}
    for key, name in (("intro", "intro.wav"), ("stinger", "stinger.wav"), ("outro", "outro.wav")):
        path = ASSETS_DIR / name
        out[key] = len(AudioSegment.from_file(str(path))) if path.exists() else 0
    return out


def _chapter_title(segment_type: str, topic: str | None) -> str:
    if segment_type == "cold_open":
        return "Cold open"
    if segment_type == "intro":
        return "Intro"
    if segment_type == "sign_off":
        return "Sign-off & predictions"
    return topic or segment_type.replace("_", " ").title()


def assemble_episode(
    audio_manifest: list[dict], output_dir: Path, roster: list[str] | None = None
) -> Path:
    """
    Stitch all audio segments into a single episode MP3.

    Structure: intro sting -> segments (stinger between each) -> outro sting.
    Writes chapters.json (segment titles + start times) next to the MP3.

    Returns the path to the final episode MP3.
    """
    if not audio_manifest:
        raise ValueError("No audio segments to assemble")

    intro = _load_sting("intro.wav")
    stinger = _load_sting("stinger.wav")
    outro = _load_sting("outro.wav")

    episode = intro if intro else AudioSegment.silent(duration=500)
    episode += AudioSegment.silent(duration=PAUSE_AFTER_INTRO)

    chapters: list[dict] = []
    prev_speaker = None
    prev_key = None  # (segment_type, topic) — a new topic IS a new segment

    for entry in audio_manifest:
        audio_path = entry["audio_path"]
        speaker = entry["speaker"]
        segment_type = entry["segment_type"]
        seg_key = (segment_type, entry.get("topic"))

        try:
            segment_audio = AudioSegment.from_mp3(str(audio_path))
        except Exception as e:
            logger.error(f"Failed to load {audio_path}: {e}")
            continue

        if prev_key is not None and seg_key != prev_key:
            # Segment boundary: pad, sting, pad
            episode += AudioSegment.silent(duration=STINGER_PAD)
            if stinger:
                episode += stinger
            episode += AudioSegment.silent(duration=STINGER_PAD)
        elif prev_speaker is not None and speaker != prev_speaker:
            episode += AudioSegment.silent(duration=PAUSE_BETWEEN_LINES)
        elif prev_speaker is not None:
            episode += AudioSegment.silent(duration=PAUSE_WITHIN_SPEAKER)

        if seg_key != prev_key:
            chapters.append({
                "title": _chapter_title(segment_type, entry.get("topic")),
                "start_ms": len(episode),
            })

        episode += segment_audio

        prev_speaker = speaker
        prev_key = seg_key

    # Outro: pad, sting, tail silence
    episode += AudioSegment.silent(duration=PAUSE_BEFORE_OUTRO)
    if outro:
        episode += outro
    episode += AudioSegment.silent(duration=OUTRO_SILENCE)

    # Normalize volume
    episode = normalize(episode)

    # Export
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "episode.mp3"
    episode.export(
        str(output_path),
        format="mp3",
        bitrate="192k",
        tags={
            "title": config.PODCAST_TITLE,
            "artist": " & ".join(roster) if roster else "Claude & ChatGPT",
            "album": config.PODCAST_TITLE,
            "genre": "Podcast",
        },
    )

    # Chapters — first entry must start at 0:00 for YouTube to accept them
    if chapters:
        chapters[0]["start_ms"] = 0
    (output_dir / "chapters.json").write_text(
        json.dumps(chapters, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    duration_sec = len(episode) / 1000
    logger.info(
        f"Episode assembled: {output_path} "
        f"({duration_sec:.0f}s / {duration_sec/60:.1f}min, "
        f"{len(chapters)} chapters)"
    )
    return output_path


def get_episode_duration(episode_path: Path) -> float:
    """Get duration of an episode in seconds."""
    audio = AudioSegment.from_mp3(str(episode_path))
    return len(audio) / 1000
