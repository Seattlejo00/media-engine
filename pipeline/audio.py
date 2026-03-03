"""
Audio assembly.
Stitches individual TTS segments into a full episode MP3 with
natural pauses, segment transitions, and normalized volume.
"""

import logging
from pathlib import Path

from pydub import AudioSegment
from pydub.effects import normalize

import config

logger = logging.getLogger(__name__)

# Timing constants (milliseconds)
PAUSE_BETWEEN_LINES = 400        # Natural breath pause between speakers
PAUSE_WITHIN_SPEAKER = 200       # Shorter pause when same speaker continues
PAUSE_BETWEEN_SEGMENTS = 1200    # Longer pause between segments (topic change)
INTRO_SILENCE = 500              # Silence at the start
OUTRO_SILENCE = 1500             # Silence at the end


def assemble_episode(
    audio_manifest: list[dict], output_dir: Path, roster: list[str] | None = None
) -> Path:
    """
    Stitch all audio segments into a single episode MP3.

    Args:
        audio_manifest: List of dicts from tts.synthesize_script()
        output_dir: Directory to save the final episode

    Returns:
        Path to the final episode MP3.
    """
    if not audio_manifest:
        raise ValueError("No audio segments to assemble")

    episode = AudioSegment.silent(duration=INTRO_SILENCE)
    prev_speaker = None
    prev_segment = None

    for entry in audio_manifest:
        audio_path = entry["audio_path"]
        speaker = entry["speaker"]
        segment_type = entry["segment_type"]

        try:
            segment_audio = AudioSegment.from_mp3(str(audio_path))
        except Exception as e:
            logger.error(f"Failed to load {audio_path}: {e}")
            continue

        # Determine pause length
        if prev_segment is not None and segment_type != prev_segment:
            pause = PAUSE_BETWEEN_SEGMENTS
        elif prev_speaker is not None and speaker != prev_speaker:
            pause = PAUSE_BETWEEN_LINES
        elif prev_speaker is not None:
            pause = PAUSE_WITHIN_SPEAKER
        else:
            pause = 0

        episode += AudioSegment.silent(duration=pause)
        episode += segment_audio

        prev_speaker = speaker
        prev_segment = segment_type

    # Add outro silence
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

    duration_sec = len(episode) / 1000
    logger.info(
        f"Episode assembled: {output_path} "
        f"({duration_sec:.0f}s / {duration_sec/60:.1f}min)"
    )
    return output_path


def get_episode_duration(episode_path: Path) -> float:
    """Get duration of an episode in seconds."""
    audio = AudioSegment.from_mp3(str(episode_path))
    return len(audio) / 1000
