"""
Video generator.
Creates video from the podcast audio with animated visuals:
- Speaker indicators (who's talking)
- Animated waveform or equalizer
- Captions/subtitles
- Branded overlays
"""

import json
import logging
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    TextClip,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFont

import config

logger = logging.getLogger(__name__)

# Fonts — use full paths on Windows, fallback for other OS
import platform
if platform.system() == "Windows":
    FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
    FONT_REGULAR = "C:/Windows/Fonts/arial.ttf"
else:
    FONT_BOLD = "Arial-Bold"
    FONT_REGULAR = "Arial"

# Video dimensions
LANDSCAPE = (1920, 1080)  # YouTube
PORTRAIT = (1080, 1920)   # TikTok / Reels / Shorts

# Colors
BG_COLOR = (10, 10, 20)           # Dark background
TEXT_COLOR = (255, 255, 255)
SUBTITLE_BG = (0, 0, 0)


def _create_speaker_frame(
    speaker: str,
    text: str,
    duration: float,
    size: tuple[int, int] = LANDSCAPE,
) -> CompositeVideoClip:
    """Create a single video frame showing who's speaking with subtitles."""
    width, height = size
    is_landscape = size == LANDSCAPE

    # Background
    bg = ColorClip(size=size, color=BG_COLOR).with_duration(duration)

    # Speaker indicator bar at top — color from registry
    color = config.SPEAKERS.get(speaker, config.SPEAKERS["ChatGPT"])["color"]
    speaker_bar = ColorClip(
        size=(width, 8), color=color
    ).with_duration(duration).with_position((0, 0))

    # Speaker icon (colored circle)
    icon_size = 100 if is_landscape else 80
    icon_y = int(height * 0.12) if is_landscape else int(height * 0.08)
    icon = ColorClip(
        size=(icon_size, icon_size), color=color
    ).with_duration(duration).with_position(
        ((width - icon_size) // 2, icon_y)
    )

    # Speaker name — explicit height prevents descender clipping (g, p, y in "ChatGPT")
    name_y = icon_y + icon_size + 20
    name_font_size = 44 if is_landscape else 36
    name_height = int(name_font_size * 1.8)  # generous height for descenders + stroke
    speaker_label = TextClip(
        text=speaker,
        font_size=name_font_size,
        color="white",
        font=FONT_BOLD,
        stroke_color="black",
        stroke_width=2,
        text_align="center",
        size=(None, name_height),
    ).with_duration(duration).with_position(("center", name_y))

    # Subtitle text — constrain width, limit lines, center in middle zone
    max_chars = 45 if is_landscape else 28
    wrapped = _wrap_text(text, max_chars)

    # Scale font and line count based on text length so nothing gets cut off
    lines = wrapped.split("\n")
    num_lines = len(lines)

    if is_landscape:
        if num_lines <= 5:
            sub_font_size = 32
            max_lines = 5
        elif num_lines <= 7:
            sub_font_size = 26
            max_lines = 7
        else:
            sub_font_size = 22
            max_lines = 9
    else:
        if num_lines <= 5:
            sub_font_size = 28
            max_lines = 5
        elif num_lines <= 7:
            sub_font_size = 22
            max_lines = 7
        else:
            sub_font_size = 18
            max_lines = 9

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "..."
    wrapped = "\n".join(lines)
    subtitle_y = name_y + name_height + 40  # breathing room below name

    # For portrait, constrain subtitle height so it never bleeds into bottom zone
    # Bottom safe zone for Shorts: keep everything above 78% of height
    bottom_safe = int(height * 0.78) if not is_landscape else int(height * 0.88)
    max_subtitle_h = bottom_safe - subtitle_y - 20  # 20px breathing room

    subtitle = TextClip(
        text=wrapped,
        font_size=sub_font_size,
        color="white",
        font=FONT_REGULAR,
        text_align="center",
        stroke_color="black",
        stroke_width=1,
        size=(width - 200, max_subtitle_h),
    ).with_duration(duration).with_position(("center", subtitle_y))

    # Show title / watermark — keep above YouTube Shorts bottom UI
    watermark_font_size = 20
    watermark_height = int(watermark_font_size * 2.0)
    watermark_y = int(height * 0.90) if is_landscape else int(height * 0.80)
    title = TextClip(
        text="THE AI DAILY",
        font_size=watermark_font_size,
        color=(120, 120, 120),
        font=FONT_BOLD,
        size=(None, watermark_height),
    ).with_duration(duration).with_position(("center", watermark_y))

    return CompositeVideoClip(
        [bg, speaker_bar, icon, speaker_label, subtitle, title], size=size
    )


def _wrap_text(text: str, max_chars: int) -> str:
    """Word-wrap text to fit within max characters per line."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        if len(current_line) + len(word) + 1 <= max_chars:
            current_line += (" " if current_line else "") + word
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return "\n".join(lines)


def _estimate_duration(audio_path: Path) -> float:
    """Get duration of an audio segment."""
    clip = AudioFileClip(str(audio_path))
    duration = clip.duration
    clip.close()
    return duration


def generate_video(
    audio_manifest: list[dict],
    episode_audio_path: Path,
    script: dict,
    output_dir: Path,
    size: tuple[int, int] = LANDSCAPE,
) -> Path:
    """
    Generate a full video for the episode.

    Combines speaker frames synced to audio segments into a complete video.
    """
    logger.info(f"Generating {'landscape' if size == LANDSCAPE else 'portrait'} video...")

    clips = []

    for entry in audio_manifest:
        duration = _estimate_duration(entry["audio_path"])
        speaker = entry["speaker"]
        text = entry["text"]

        frame = _create_speaker_frame(speaker, text, duration, size)
        clips.append(frame)

    if not clips:
        raise ValueError("No video clips to assemble")

    # Concatenate all clips
    video = concatenate_videoclips(clips, method="compose")

    # Add the full episode audio
    audio = AudioFileClip(str(episode_audio_path))
    # Trim video to match audio length (may differ slightly due to pauses in audio assembly)
    if video.duration > audio.duration:
        video = video.subclipped(0, audio.duration)
    video = video.with_audio(audio)

    # Export
    suffix = "landscape" if size == LANDSCAPE else "portrait"
    output_path = output_dir / f"episode_{suffix}.mp4"

    video.write_videofile(
        str(output_path),
        fps=1,  # Static frames, no motion — 1fps is fine and 24x faster
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        logger="bar",
    )

    video.close()
    audio.close()

    logger.info(f"Video saved: {output_path}")
    return output_path


def generate_landscape_video(
    audio_manifest: list[dict],
    episode_audio_path: Path,
    script: dict,
    output_dir: Path,
) -> Path:
    """Generate YouTube-format landscape video."""
    return generate_video(
        audio_manifest, episode_audio_path, script, output_dir, LANDSCAPE
    )
