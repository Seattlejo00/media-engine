"""
Thumbnail generator.
Creates YouTube-optimized thumbnails (1280x720) with:
- A short, mobile-readable story hook
- Speaker color accents
- Dark cinematic background
- Clear, consistently positioned show label
"""

import logging
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config

logger = logging.getLogger(__name__)

# Thumbnail size (YouTube recommended)
THUMB_SIZE = (1280, 720)

# Fonts — use full paths on Windows
import platform
if platform.system() == "Windows":
    FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
    FONT_REGULAR = "C:/Windows/Fonts/arial.ttf"
elif platform.system() == "Darwin":
    FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
else:
    FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _wrap_text_pil(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    return lines


def _thumbnail_hook(script: dict, topics: list[dict], max_words: int = 7) -> str:
    """Return a compact hook instead of reproducing an article headline."""
    candidate = script.get("youtube_title") or ""
    candidate = re.split(r"\s(?:\||—|-)\s(?:The\s+)?Context Window", candidate, maxsplit=1, flags=re.I)[0]
    if not candidate:
        main_topics = [t for t in topics if t.get("category") == "main"]
        candidate = (main_topics[0].get("title") if main_topics else "") or script.get("title", "AI News")
    candidate = re.sub(r"\s+", " ", candidate).strip(" -—|:")
    words = candidate.split()
    return " ".join(words[:max_words]).rstrip(".,;:—-")


def generate_thumbnail(
    script: dict,
    topics: list[dict],
    output_dir: Path,
    roster: list[str] | None = None,
) -> Path:
    """
    Generate a YouTube thumbnail for the episode.

    Returns path to the thumbnail PNG.
    """
    if roster is None:
        roster = config.get_hosts()

    width, height = THUMB_SIZE
    img = Image.new("RGB", THUMB_SIZE, color=(9, 10, 24))
    draw = ImageDraw.Draw(img)

    # --- Gradient accent bar at top (uses first speaker's color) ---
    primary_color = config.SPEAKERS.get(roster[0], config.SPEAKERS["Claude"])["color"]
    secondary_color = config.SPEAKERS.get(roster[-1], config.SPEAKERS["ChatGPT"])["color"]

    # Strong dual-host frame that remains identifiable at thumbnail size.
    draw.rectangle([0, 0, 14, height], fill=primary_color)
    draw.rectangle([width - 14, 0, width, height], fill=secondary_color)
    draw.rectangle([14, 0, width - 14, 9], fill=(38, 40, 69))

    # --- Main headline text ---
    headline = _thumbnail_hook(script, topics).upper()
    max_text_width = width - 170
    max_lines = 2
    max_text_height = 300

    headline_font = None
    headline_lines = []
    line_height = 0

    for font_size in range(104, 50, -2):
        try:
            test_font = ImageFont.truetype(FONT_BOLD, font_size)
        except (OSError, IOError):
            test_font = ImageFont.load_default()
        test_lines = _wrap_text_pil(headline, test_font, max_text_width)
        test_line_height = int(font_size * 1.25)
        total_h = len(test_lines) * test_line_height

        if len(test_lines) <= max_lines and total_h <= max_text_height:
            headline_font = test_font
            headline_lines = test_lines
            line_height = test_line_height
            break

    # Fallback if nothing fit
    if headline_font is None:
        try:
            headline_font = ImageFont.truetype(FONT_BOLD, 30)
        except (OSError, IOError):
            headline_font = ImageFont.load_default()
        headline_lines = _wrap_text_pil(headline, headline_font, max_text_width)[:max_lines]
        line_height = 38

    # Keep the hook in a fixed editorial safe zone.
    total_text_height = len(headline_lines) * line_height
    start_y = 240 + (max_text_height - total_text_height) // 2

    for i, line in enumerate(headline_lines):
        y = start_y + i * line_height
        # Text shadow for readability
        draw.text((87, y + 4), line, font=headline_font, fill=(0, 0, 0))
        draw.text((83, y), line, font=headline_font, fill=(245, 243, 235))

    # Compact show label: visible, consistent, and never cropped.
    try:
        label_font = ImageFont.truetype(FONT_BOLD, 24)
        brand_font = ImageFont.truetype(FONT_BOLD, 29)
    except (OSError, IOError):
        label_font = brand_font = ImageFont.load_default()
    draw.text((83, 68), "AI NEWS  •  10 MINUTES", font=label_font, fill=(145, 148, 170))
    draw.text((83, 112), "THE CONTEXT WINDOW", font=brand_font, fill=(245, 243, 235))

    # --- Speaker indicator dots at bottom ---
    dot_y = height - 76
    dot_size = 14
    dot_start_x = 83

    try:
        name_font = ImageFont.truetype(FONT_BOLD, 22)
    except (OSError, IOError):
        name_font = ImageFont.load_default()

    for i, speaker in enumerate(roster):
        color = config.SPEAKERS.get(speaker, config.SPEAKERS["ChatGPT"])["color"]
        x = dot_start_x + i * 190

        # Colored dot
        draw.ellipse(
            [x, dot_y, x + dot_size, dot_y + dot_size],
            fill=color,
        )

        # Speaker name next to dot
        draw.text(
            (x + dot_size + 8, dot_y + 2),
            speaker,
            font=name_font, fill=(185, 187, 202),
        )

    # --- Episode number / subtle detail top right ---
    try:
        detail_font = ImageFont.truetype(FONT_REGULAR, 20)
    except (OSError, IOError):
        detail_font = ImageFont.load_default()

    topic_count = len(topics)
    detail_text = f"{topic_count} STORIES"
    detail_width = draw.textbbox((0, 0), detail_text, font=detail_font)[2]
    draw.text((width - 83 - detail_width, height - 73), detail_text,
              font=detail_font, fill=(100, 103, 127))

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = output_dir / "thumbnail.png"
    img.save(str(thumb_path), "PNG", quality=95)

    logger.info(f"Thumbnail generated: {thumb_path}")
    return thumb_path
