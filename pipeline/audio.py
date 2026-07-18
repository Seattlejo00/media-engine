"""
Audio assembly.
Builds the episode on an overlay timeline: music crossfades under
full-level speech at every seam (intro fades out under the first words,
the segue breathes in and out around segment changes, the outro fades in
under the closing words). Every spoken line is loudness-matched so no
host is quieter than another. Also emits chapter timings for YouTube.
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
INTRO_OVERLAP = 1500             # Intro music fades out under the first words
SEG_OVERLAP = 800                # Segue fades in under the speech tail and
                                 # out under the next segment's opener
OUTRO_OVERLAP = 1500             # Outro fades in under the closing words
TAIL_SILENCE = 300               # Breath at the very end

# Loudness target for every spoken line — keeps Claude and ChatGPT at
# the same level so listeners never ride the volume knob. Music assets
# in assets/ are pre-leveled ~5dB below this.
TARGET_DBFS = -20.0

ASSETS_DIR = config.BASE_DIR / "assets"
FRAME_RATE = 44100


def _load_sting(name: str) -> AudioSegment | None:
    """Load a music asset; None if missing (assembly degrades gracefully)."""
    path = ASSETS_DIR / name
    if not path.exists():
        logger.warning(f"Missing audio asset {path} — continuing without it")
        return None
    return AudioSegment.from_file(str(path))


def sting_durations_ms() -> dict[str, int]:
    """Durations of the music pieces — the video mirrors these exactly."""
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


def _stereo(seg: AudioSegment) -> AudioSegment:
    return seg.set_frame_rate(FRAME_RATE).set_channels(2)


def assemble_episode(
    audio_manifest: list[dict], output_dir: Path, roster: list[str] | None = None
) -> Path:
    """
    Assemble the episode MP3 on an overlay timeline.

    Speech blocks (one per segment) sit at full level; music is placed
    underneath with fades so every seam crossfades instead of cutting.
    Writes chapters.json (segment titles + start times) next to the MP3.
    """
    if not audio_manifest:
        raise ValueError("No audio segments to assemble")

    intro = _load_sting("intro.wav")
    stinger = _load_sting("stinger.wav")
    outro = _load_sting("outro.wav")

    # --- Build one speech block per segment (lines + natural pauses) ---
    blocks: list[dict] = []
    current: dict | None = None
    prev_speaker = None
    prev_key = None  # (segment_type, topic) — a new topic IS a new segment

    for entry in audio_manifest:
        seg_key = (entry["segment_type"], entry.get("topic"))
        try:
            line = AudioSegment.from_mp3(str(entry["audio_path"]))
        except Exception as e:
            logger.error(f"Failed to load {entry['audio_path']}: {e}")
            continue

        # Loudness-match every line to the same target
        line = line.apply_gain(TARGET_DBFS - line.dBFS)

        if seg_key != prev_key:
            current = {
                "title": _chapter_title(entry["segment_type"], entry.get("topic")),
                "audio": line,
            }
            blocks.append(current)
        else:
            gap = (
                PAUSE_BETWEEN_LINES if entry["speaker"] != prev_speaker
                else PAUSE_WITHIN_SPEAKER
            )
            current["audio"] += AudioSegment.silent(duration=gap) + line

        prev_speaker = entry["speaker"]
        prev_key = seg_key

    if not blocks:
        raise ValueError("No usable audio segments")

    # --- Place blocks and music on the timeline ---
    events: list[tuple[int, AudioSegment]] = []
    chapters: list[dict] = []

    if intro:
        events.append((0, intro.fade_out(INTRO_OVERLAP)))
        cursor = max(len(intro) - INTRO_OVERLAP, 0)
    else:
        cursor = 0

    for i, block in enumerate(blocks):
        if i > 0:
            if stinger:
                seg_start = max(cursor - SEG_OVERLAP, 0)
                events.append(
                    (seg_start, stinger.fade_in(SEG_OVERLAP).fade_out(SEG_OVERLAP))
                )
                cursor = seg_start + len(stinger) - SEG_OVERLAP
            else:
                cursor += 2 * PAUSE_BETWEEN_LINES

        chapters.append({"title": block["title"], "start_ms": cursor})
        events.append((cursor, block["audio"]))
        cursor += len(block["audio"])

    if outro:
        outro_start = max(cursor - OUTRO_OVERLAP, 0)
        events.append((outro_start, outro.fade_in(OUTRO_OVERLAP)))
        cursor = outro_start + len(outro)

    total = cursor + TAIL_SILENCE

    canvas = AudioSegment.silent(duration=total, frame_rate=FRAME_RATE).set_channels(2)
    for position, seg in events:
        canvas = canvas.overlay(_stereo(seg), position=position)

    episode = normalize(canvas)

    # --- Export ---
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
        f"{len(chapters)} chapters, crossfaded)"
    )
    return output_path


def get_episode_duration(episode_path: Path) -> float:
    """Get duration of an episode in seconds."""
    audio = AudioSegment.from_mp3(str(episode_path))
    return len(audio) / 1000
