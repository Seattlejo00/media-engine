"""
Thumbnail generator.
Creates YouTube-optimized thumbnails (1280x720) with:
- Bold topic text
- Speaker color accents
- Dark cinematic background
- Brand watermark
"""

import logging
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
    img = Image.new("RGB", THUMB_SIZE, color=(10, 10, 25))
    draw = ImageDraw.Draw(img)

    # --- Gradient accent bar at top (uses first speaker's color) ---
    primary_color = config.SPEAKERS.get(roster[0], config.SPEAKERS["Claude"])["color"]
    secondary_color = config.SPEAKERS.get(roster[-1], config.SPEAKERS["ChatGPT"])["color"]

    # Top accent bar — gradient-like effect using two color blocks
    bar_height = 8
    draw.rectangle([0, 0, width // 2, bar_height], fill=primary_color)
    draw.rectangle([width // 2, 0, width, bar_height], fill=secondary_color)

    # --- Main headline text ---
    # Use the lead main story as the hook
    main_topics = [t for t in topics if t.get("category") == "main"]
    if main_topics:
        headline = main_topics[0]["title"]
    else:
        headline = script.get("title", "The AI Daily")

    # Keep headline punchy — max ~50 chars
    if len(headline) > 55:
        headline = headline[:52] + "..."

    try:
        headline_font = ImageFont.truetype(FONT_BOLD, 64)
    except (OSError, IOError):
        headline_font = ImageFont.load_default()

    headline_lines = _wrap_text_pil(headline, headline_font, width - 160)
    headline_lines = headline_lines[:3]  # max 3 lines

    # Center the headline block vertically
    line_height = 78
    total_text_height = len(headline_lines) * line_height
    start_y = (height - total_text_height) // 2 - 40

    for i, line in enumerate(headline_lines):
        y = start_y + i * line_height
        # Text shadow for readability
        draw.text((82, y + 2), line, font=headline_font, fill=(0, 0, 0))
        draw.text((80, y), line, font=headline_font, fill=(255, 255, 255))

    # --- Speaker indicator dots at bottom ---
    dot_y = height - 120
    dot_size = 24
    total_dots_width = len(roster) * (dot_size + 40) - 40
    dot_start_x = (width - total_dots_width) // 2

    try:
        name_font = ImageFont.truetype(FONT_BOLD, 22)
    except (OSError, IOError):
        name_font = ImageFont.load_default()

    for i, speaker in enumerate(roster):
        color = config.SPEAKERS.get(speaker, config.SPEAKERS["ChatGPT"])["color"]
        x = dot_start_x + i * (dot_size + 80)

        # Colored dot
        draw.ellipse(
            [x, dot_y, x + dot_size, dot_y + dot_size],
            fill=color,
        )

        # Speaker name next to dot
        draw.text(
            (x + dot_size + 8, dot_y + 2),
            speaker,
            font=name_font,
            fill=(200, 200, 200),
        )

    # --- Brand watermark bottom right ---
    try:
        brand_font = ImageFont.truetype(FONT_BOLD, 28)
    except (OSError, IOError):
        brand_font = ImageFont.load_default()

    draw.text(
        (width - 250, height - 50),
        "THE AI DAILY",
        font=brand_font,
        fill=(100, 100, 120),
    )

    # --- Episode number / subtle detail top right ---
    try:
        detail_font = ImageFont.truetype(FONT_REGULAR, 20)
    except (OSError, IOError):
        detail_font = ImageFont.load_default()

    topic_count = len(topics)
    detail_text = f"{topic_count} stories"
    draw.text(
        (width - 140, 20),
        detail_text,
        font=detail_font,
        fill=(80, 80, 100),
    )

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = output_dir / "thumbnail.png"
    img.save(str(thumb_path), "PNG", quality=95)

    logger.info(f"Thumbnail generated: {thumb_path}")
    return thumb_path
