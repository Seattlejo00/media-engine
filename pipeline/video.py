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
    ImageClip,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

logger = logging.getLogger(__name__)

# Fonts — use full paths on Windows, fallback for other OS
import platform
if platform.system() == "Windows":
    FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
    FONT_REGULAR = "C:/Windows/Fonts/arial.ttf"
else:
    FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Video dimensions
LANDSCAPE = (1920, 1080)  # YouTube
PORTRAIT = (1080, 1920)   # TikTok / Reels / Shorts

# Colors
BG_COLOR = (10, 10, 20)           # Dark background
TEXT_COLOR = (255, 255, 255)
SUBTITLE_BG = (0, 0, 0)


# Design palette
BG_TOP = (11, 12, 24)       # near-black navy
BG_BOTTOM = (24, 22, 48)    # deep indigo
PANEL_FILL = (0, 0, 0, 150)  # subtitle panel (RGBA)
MUTED_TEXT = (158, 160, 184)

# Backgrounds are expensive (gaussian-blurred glow) but identical for every
# line a speaker says — cache per (speaker, size).
_BG_CACHE: dict = {}


def _font(path: str, px: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, px)
    except OSError:
        return ImageFont.load_default(px)


def _background(speaker: str, size: tuple[int, int]) -> Image.Image:
    """Vertical gradient + soft glow in the speaker's color, cached."""
    key = (speaker, size)
    if key in _BG_CACHE:
        return _BG_CACHE[key]

    width, height = size
    color = config.SPEAKERS.get(speaker, config.SPEAKERS["ChatGPT"])["color"]

    img = Image.new("RGB", size)
    # Vertical gradient, drawn row by row
    for y in range(height):
        t = y / max(height - 1, 1)
        row = tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM))
        img.paste(row, (0, y, width, y + 1))

    # Soft radial glow behind the speaker area, in their color
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    is_landscape = width > height
    cx, cy = width // 2, int(height * (0.24 if is_landscape else 0.26))
    r = int(min(width, height) * 0.38)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=r // 2))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    _BG_CACHE[key] = img
    return img


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font_path: str,
              px: int, max_width: int, min_px: int = 20) -> ImageFont.FreeTypeFont:
    """Shrink font size until text fits max_width."""
    font = _font(font_path, px)
    while px > min_px and draw.textlength(text, font=font) > max_width:
        px -= 2
        font = _font(font_path, px)
    return font


def _render_frame_image(
    speaker: str,
    text: str,
    size: tuple[int, int],
    topic: str | None = None,
) -> Image.Image:
    """Draw one fully-styled still frame (PIL) for a spoken line."""
    width, height = size
    is_landscape = width > height
    color = config.SPEAKERS.get(speaker, config.SPEAKERS["ChatGPT"])["color"]
    company = config.SPEAKERS.get(speaker, {}).get("company", "")

    img = _background(speaker, size).copy()
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    margin = 80 if is_landscape else 56

    # --- Topic banner (top) ---
    banner_bottom = int(height * 0.06)
    if topic:
        eyebrow_font = _font(FONT_BOLD, 26 if is_landscape else 30)
        draw.text((margin, banner_bottom), "TODAY'S STORY", font=eyebrow_font, fill=(*color, 255))
        headline_y = banner_bottom + (40 if is_landscape else 46)
        headline_font = _fit_text(
            draw, topic, FONT_BOLD, 42 if is_landscape else 40, width - 2 * margin
        )
        draw.text((margin, headline_y), topic, font=headline_font, fill=(255, 255, 255, 255))
        rule_y = headline_y + headline_font.size + 22
        draw.rectangle([margin, rule_y, width - margin, rule_y + 3], fill=(*color, 160))
        banner_bottom = rule_y

    # --- Speaker avatar (colored circle + initial) ---
    r = 70 if is_landscape else 84
    cx = width // 2
    cy = int(height * (0.24 if is_landscape else 0.26))
    # outer ring
    draw.ellipse([cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8],
                 outline=(*color, 200), width=4)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, 255))
    initial_font = _font(FONT_BOLD, int(r * 1.1))
    draw.text((cx, cy), speaker[0], font=initial_font, fill=(255, 255, 255, 255), anchor="mm")

    # --- Name + company ---
    name_font = _font(FONT_BOLD, 48 if is_landscape else 52)
    name_y = cy + r + 36
    draw.text((cx, name_y), speaker, font=name_font, fill=(255, 255, 255, 255), anchor="ma")
    company_font = _font(FONT_REGULAR, 26 if is_landscape else 30)
    draw.text((cx, name_y + name_font.size + 12), company,
              font=company_font, fill=(*MUTED_TEXT, 255), anchor="ma")

    # --- Subtitle panel ---
    max_chars = 46 if is_landscape else 26
    lines = _wrap_text(text, max_chars).split("\n")

    if is_landscape:
        sub_px, max_lines = (34, 5) if len(lines) <= 5 else (28, 7) if len(lines) <= 7 else (24, 9)
    else:
        sub_px, max_lines = (40, 6) if len(lines) <= 6 else (32, 8) if len(lines) <= 8 else (26, 10)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "..."

    sub_font = _font(FONT_REGULAR, sub_px)
    line_h = int(sub_px * 1.4)
    block_h = line_h * len(lines)
    block_w = max((int(draw.textlength(l, font=sub_font)) for l in lines), default=0)

    company_bottom = name_y + name_font.size + 12 + company_font.size
    sub_top = company_bottom + 60
    bottom_safe = int(height * (0.88 if is_landscape else 0.78))
    # Pull up if the block would breach the safe zone, but never over the name
    sub_top = max(min(sub_top, bottom_safe - block_h - 40), company_bottom + 36)

    pad_x, pad_y = 44, 30
    panel = [cx - block_w // 2 - pad_x, sub_top - pad_y,
             cx + block_w // 2 + pad_x, sub_top + block_h + pad_y]
    draw.rounded_rectangle(panel, radius=24, fill=PANEL_FILL)
    # accent tick on the left edge of the panel
    draw.rounded_rectangle([panel[0], panel[1] + 18, panel[0] + 6, panel[3] - 18],
                           radius=3, fill=(*color, 220))
    for i, line in enumerate(lines):
        draw.text((cx, sub_top + i * line_h), line, font=sub_font,
                  fill=(240, 240, 245, 255), anchor="ma")

    # --- Watermark ---
    wm_font = _font(FONT_BOLD, 24 if is_landscape else 28)
    wm_y = int(height * (0.94 if is_landscape else 0.815))
    draw.text((cx, wm_y), "THE CONTEXT WINDOW", font=wm_font, fill=(*MUTED_TEXT, 200), anchor="ma")

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _create_speaker_frame(
    speaker: str,
    text: str,
    duration: float,
    size: tuple[int, int] = LANDSCAPE,
    topic: str | None = None,
):
    """Create a single video frame showing who's speaking with subtitles."""
    frame = _render_frame_image(speaker, text, size, topic=topic)
    return ImageClip(np.asarray(frame)).with_duration(duration)


def _topic_by_index(script: dict) -> dict[int, str | None]:
    """
    Map each global dialogue-line index to its segment's topic.

    Mirrors the index assignment in tts.synthesize_script (skips empty
    lines) so manifest entries line up with their story headline.
    """
    mapping: dict[int, str | None] = {}
    idx = 0
    for segment in script.get("segments", []):
        topic = (segment.get("topic") or "").strip() or None
        for line in segment.get("dialogue", []):
            if not (line.get("text") or "").strip():
                continue
            mapping[idx] = topic
            idx += 1
    return mapping


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

    # The assembled episode audio inserts pauses between lines/segments
    # (see pipeline.audio). Each frame must cover its line's audio PLUS the
    # pause before it, or subtitles drift ahead of the audio and cut
    # speakers off before they finish.
    from pipeline.audio import (
        INTRO_SILENCE,
        PAUSE_BETWEEN_LINES,
        PAUSE_BETWEEN_SEGMENTS,
        PAUSE_WITHIN_SPEAKER,
    )

    clips = []
    topic_map = _topic_by_index(script)
    prev_speaker = None
    prev_segment = None

    for entry in audio_manifest:
        duration = _estimate_duration(entry["audio_path"])
        speaker = entry["speaker"]
        text = entry["text"]
        segment_type = entry.get("segment_type")

        # Same pause rules as pipeline.audio.assemble_episode
        if prev_segment is not None and segment_type != prev_segment:
            pause_ms = PAUSE_BETWEEN_SEGMENTS
        elif prev_speaker is not None and speaker != prev_speaker:
            pause_ms = PAUSE_BETWEEN_LINES
        elif prev_speaker is not None:
            pause_ms = PAUSE_WITHIN_SPEAKER
        else:
            pause_ms = INTRO_SILENCE

        frame = _create_speaker_frame(
            speaker,
            text,
            duration + pause_ms / 1000.0,
            size,
            topic=topic_map.get(entry.get("index")),
        )
        clips.append(frame)
        prev_speaker = speaker
        prev_segment = segment_type

    if not clips:
        raise ValueError("No video clips to assemble")

    # Pad the last frame to the exact audio length — covers the outro
    # silence plus any accumulated rounding drift.
    audio = AudioFileClip(str(episode_audio_path))
    total = sum(c.duration for c in clips)
    if total < audio.duration:
        clips[-1] = clips[-1].with_duration(
            clips[-1].duration + (audio.duration - total)
        )

    # Concatenate all clips
    video = concatenate_videoclips(clips, method="compose")

    # Trim any residual overrun so video and audio end together
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
