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
from functools import lru_cache
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    ImageClip,
    VideoClip,
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

YOUTUBE_OUTRO_URL = "youtube.com/@TheContextWindow-q1z"
SPOTIFY_OUTRO_URL = "open.spotify.com/show/033OoZlyZBlEwCd6kmNdpT"

# Backgrounds are expensive (gaussian-blurred glow) but identical for every
# line a speaker says — cache per (speaker, size).
_BG_CACHE: dict = {}
PIXEL_ANCHOR_DIR = config.BASE_DIR / "assets" / "pixel_anchors"
ANIMATION_FPS = 8
_NEWSROOM_SPEAKERS = frozenset({"ChatGPT", "Claude"})
_BUBBLE_BOXES = {
    "ChatGPT": (24, 142, 336, 367),
    "Claude": (1325, 142, 1648, 367),
}


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


def _newsroom_supported(speaker: str) -> bool:
    """Return whether the layered newsroom art supports this speaker."""
    return speaker in _NEWSROOM_SPEAKERS and (
        PIXEL_ANCHOR_DIR / "newsroom.png"
    ).is_file()


@lru_cache(maxsize=8)
def _newsroom_source(
    speaker: str, mouth_open: bool = False, blink: bool = False
) -> Image.Image:
    """Compose one stable source frame from the base and sparse face layers."""
    with Image.open(PIXEL_ANCHOR_DIR / "newsroom.png") as source:
        frame = source.convert("RGBA")

    states = []
    if mouth_open:
        states.append("talk")
    if blink:
        states.append("blink")
    for state in states:
        path = PIXEL_ANCHOR_DIR / f"{speaker.lower()}_{state}.png"
        if path.is_file():
            with Image.open(path) as overlay:
                frame.alpha_composite(overlay.convert("RGBA"))
    return frame.convert("RGB")


def _newsroom_canvas(
    speaker: str,
    size: tuple[int, int],
    mouth_open: bool,
    blink: bool,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Scale the two-anchor set for landscape or crop one anchor for Shorts."""
    source = _newsroom_source(speaker, mouth_open, blink)
    source_width, source_height = source.size
    width, height = size
    bubble = _BUBBLE_BOXES[speaker]

    if width > height:
        canvas = source.resize(size, Image.Resampling.NEAREST)
        sx, sy = width / source_width, height / source_height
        bubble_box = tuple(
            int(value * (sx if index % 2 == 0 else sy))
            for index, value in enumerate(bubble)
        )
        return canvas, bubble_box

    half = source_width // 2
    crop_left = 0 if speaker == "ChatGPT" else half
    crop = source.crop((crop_left, 0, crop_left + half, source_height))
    scale = width / crop.width
    scaled_height = int(crop.height * scale)
    crop = crop.resize((width, scaled_height), Image.Resampling.NEAREST)

    canvas = _background(speaker, size).copy()
    offset_y = int(height * 0.14)
    canvas.paste(crop, (0, offset_y))
    bubble_box = (
        int((bubble[0] - crop_left) * scale),
        int(bubble[1] * scale + offset_y),
        int((bubble[2] - crop_left) * scale),
        int(bubble[3] * scale + offset_y),
    )
    return canvas, bubble_box


def _render_newsroom_frame(
    speaker: str,
    size: tuple[int, int],
    topic: str | None,
    page_lines: list[str],
    mouth_open: bool = False,
    blink: bool = False,
) -> Image.Image:
    """Render the animated-anchor scene and active speaker's speech bubble."""
    width, height = size
    is_landscape = width > height
    color = config.SPEAKERS[speaker]["color"]
    canvas, bubble = _newsroom_canvas(speaker, size, mouth_open, blink)
    draw = ImageDraw.Draw(canvas)

    if topic:
        if is_landscape:
            title = f"TODAY'S STORY  |  {topic}"
            title_font = _fit_text(
                draw, title, FONT_BOLD, 29, int(width * 0.52), min_px=20
            )
            draw.text(
                (width // 2, 30), title, font=title_font,
                fill=(235, 238, 245), anchor="ma",
            )
        else:
            eyebrow = _font(FONT_BOLD, 28)
            draw.text((54, 58), "TODAY'S STORY", font=eyebrow, fill=color)
            title_font, title_lines = _fit_wrapped_text(
                draw, topic, FONT_BOLD, 46, width - 108, 2, 30
            )
            draw.multiline_text(
                (54, 100), "\n".join(title_lines), font=title_font,
                fill=(245, 245, 248), spacing=8,
            )

    x0, y0, x1, y1 = bubble
    label_font = _font(FONT_BOLD, 25 if is_landscape else 32)
    draw.text(
        ((x0 + x1) // 2, y0 + (20 if is_landscape else 26)),
        speaker.upper(), font=label_font, fill=color, anchor="ma",
    )

    text_top = y0 + (58 if is_landscape else 70)
    max_width = x1 - x0 - (44 if is_landscape else 56)
    max_height = y1 - text_top - 22
    font_px = 27 if is_landscape else 36
    min_px = 18 if is_landscape else 25
    text = "\n".join(page_lines)
    font = _font(FONT_BOLD, font_px)
    while font_px > min_px:
        bbox = draw.multiline_textbbox(
            (0, 0), text, font=font, align="center", spacing=7
        )
        if bbox[2] - bbox[0] <= max_width and bbox[3] - bbox[1] <= max_height:
            break
        font_px -= 1
        font = _font(FONT_BOLD, font_px)
    draw.multiline_text(
        ((x0 + x1) // 2, text_top), text, font=font,
        fill=(34, 40, 52), anchor="ma", align="center", spacing=7,
    )

    wm_font = _font(FONT_BOLD, 22 if is_landscape else 27)
    draw.text(
        (width // 2, height - (18 if is_landscape else 62)),
        "THE CONTEXT WINDOW", font=wm_font, fill=(*MUTED_TEXT, 255),
        anchor="ms",
    )
    return canvas


@lru_cache(maxsize=8)
def _cached_newsroom_frame(
    speaker: str,
    size: tuple[int, int],
    topic: str | None,
    page_lines: tuple[str, ...],
    mouth_open: bool,
    blink: bool,
) -> np.ndarray:
    return np.asarray(
        _render_newsroom_frame(
            speaker, size, topic, list(page_lines), mouth_open, blink
        )
    )


def _render_frame_image(
    speaker: str,
    text: str,
    size: tuple[int, int],
    topic: str | None = None,
    page_lines: list[str] | None = None,
    mouth_open: bool = False,
    blink: bool = False,
) -> Image.Image:
    """Draw one fully-styled still frame (PIL) for a spoken line."""
    if _newsroom_supported(speaker):
        lines = page_lines or _wrap_text(text, 22).split("\n")[:5]
        return _render_newsroom_frame(
            speaker, size, topic, lines, mouth_open=mouth_open, blink=blink
        )

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

    # --- Speaker avatar fallback for guests without production art ---
    r = 70 if is_landscape else 84
    cx = width // 2
    cy = int(height * (0.24 if is_landscape else 0.26))
    draw.ellipse([cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8],
                 outline=(*color, 200), width=4)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, 255))
    initial_font = _font(FONT_BOLD, int(r * 1.1))
    initial = speaker[0] if speaker else "?"
    draw.text((cx, cy), initial, font=initial_font,
              fill=(255, 255, 255, 255), anchor="mm")

    # --- Name + company ---
    name_font = _font(FONT_BOLD, 48 if is_landscape else 52)
    name_y = cy + r + 36
    draw.text((cx, name_y), speaker, font=name_font, fill=(255, 255, 255, 255), anchor="ma")
    company_font = _font(FONT_REGULAR, 26 if is_landscape else 30)
    draw.text((cx, name_y + name_font.size + 12), company,
              font=company_font, fill=(*MUTED_TEXT, 255), anchor="ma")

    # --- Subtitle panel ---
    # page_lines comes from pagination: long lines are split across several
    # timed frames instead of being truncated with "..."
    if page_lines is not None:
        lines = page_lines
    else:
        max_chars = 46 if is_landscape else 26
        lines = _wrap_text(text, max_chars).split("\n")

    if is_landscape:
        sub_px = 34 if len(lines) <= 5 else 28 if len(lines) <= 7 else 24
    else:
        sub_px = 40 if len(lines) <= 6 else 32 if len(lines) <= 8 else 26

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


# Lines per subtitle page before splitting onto a new frame
_PAGE_LINES_LANDSCAPE = 5
_PAGE_LINES_PORTRAIT = 5


def _create_speaker_frames(
    speaker: str,
    text: str,
    duration: float,
    size: tuple[int, int] = LANDSCAPE,
    topic: str | None = None,
    speech_duration: float | None = None,
) -> list:
    """
    Create the video frame(s) for one spoken line.

    A line too long for the subtitle panel is paginated across several
    frames, each shown for a share of the audio proportional to its word
    count — nothing gets truncated.
    """
    is_landscape = size[0] > size[1]
    max_chars = (
        22 if _newsroom_supported(speaker) else (46 if is_landscape else 26)
    )
    per_page = _PAGE_LINES_LANDSCAPE if is_landscape else _PAGE_LINES_PORTRAIT

    lines = _wrap_text(text, max_chars).split("\n")
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)]

    weights = [sum(len(l.split()) for l in page) for page in pages]
    total_words = sum(weights) or 1

    frames = []
    allocated = 0.0
    speech_duration = duration if speech_duration is None else speech_duration
    for i, page in enumerate(pages):
        if i == len(pages) - 1:
            page_duration = max(duration - allocated, 0.5)
        else:
            page_duration = duration * (weights[i] / total_words)
            allocated += page_duration
        if _newsroom_supported(speaker):
            page_start = allocated - page_duration if i < len(pages) - 1 else allocated
            page_key = tuple(page)

            def frame_function(t, *, start=page_start, lines=page_key):
                line_t = start + t
                speaking = line_t < speech_duration
                blink = speaking and 3.45 <= (line_t % 3.6) <= 3.57
                mouth_open = speaking and not blink and int(line_t / 0.14) % 3 != 0
                return _cached_newsroom_frame(
                    speaker, size, topic, lines, mouth_open, blink
                )

            frames.append(VideoClip(frame_function, duration=page_duration))
        else:
            frame = _render_frame_image(
                speaker, text, size, topic=topic, page_lines=page
            )
            frames.append(ImageClip(np.asarray(frame)).with_duration(page_duration))
    return frames


def _create_speaker_frame(
    speaker: str,
    text: str,
    duration: float,
    size: tuple[int, int] = LANDSCAPE,
    topic: str | None = None,
    speech_duration: float | None = None,
):
    """Single-frame variant kept for callers that concatenate their own lists."""
    return _create_speaker_frames(
        speaker, text, duration, size, topic=topic,
        speech_duration=speech_duration,
    )


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


def _wrap_text_pixels(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    """Word-wrap text using its rendered width instead of character count."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    start_px: int,
    max_width: int,
    max_lines: int,
    min_px: int = 24,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Fit a complete headline into a bounded number of lines without clipping."""
    for px in range(start_px, min_px - 1, -2):
        font = _font(font_path, px)
        lines = _wrap_text_pixels(draw, text, font, max_width)
        if len(lines) <= max_lines and all(
            draw.textlength(line, font=font) <= max_width for line in lines
        ):
            return font, lines

    font = _font(font_path, min_px)
    return font, _wrap_text_pixels(draw, text, font, max_width)


# Brand colors for neutral (non-speaker) cards
_CARD_ACCENT = (204, 120, 50)     # Claude orange
_CARD_ACCENT2 = (16, 163, 127)    # ChatGPT green
_CARD_CACHE: dict = {}


def _card_background(size: tuple[int, int]) -> Image.Image:
    """Neutral gradient with both brand glows — the cover art look."""
    key = ("card", size)
    if key in _CARD_CACHE:
        return _CARD_CACHE[key]
    width, height = size
    img = Image.new("RGB", size)
    for y in range(height):
        t = y / max(height - 1, 1)
        row = tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM))
        img.paste(row, (0, y, width, y + 1))
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    r = int(min(width, height) * 0.4)
    gd.ellipse([width * 0.28 - r, height * 0.4 - r, width * 0.28 + r, height * 0.4 + r],
               fill=(*_CARD_ACCENT, 55))
    gd.ellipse([width * 0.72 - r, height * 0.6 - r, width * 0.72 + r, height * 0.6 + r],
               fill=(*_CARD_ACCENT2, 45))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=r // 2))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    _CARD_CACHE[key] = img
    return img


def _render_transition_card(
    kind: str, size: tuple[int, int], label: str | None = None
) -> Image.Image:
    """Full-screen card shown during the sonic-logo moments."""
    width, height = size
    is_landscape = width > height
    img = _card_background(size).copy()
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = width // 2, height // 2

    if kind == "intro":
        f1 = _font(FONT_BOLD, 110 if is_landscape else 96)
        f2 = _font(FONT_BOLD, 64 if is_landscape else 58)
        f3 = _font(FONT_REGULAR, 30 if is_landscape else 32)
        draw.text((cx, cy - int(f1.size * 1.15)), "THE CONTEXT", font=f1,
                  fill=(255, 255, 255, 255), anchor="ma")
        draw.text((cx, cy + 8), "W I N D O W", font=f2,
                  fill=(*MUTED_TEXT, 255), anchor="ma")
        draw.text((cx, cy + f2.size + 52), "AI NEWS, HOSTED BY AIS", font=f3,
                  fill=(*_CARD_ACCENT, 235), anchor="ma")

    elif kind == "upnext":
        eyebrow = _font(FONT_BOLD, 34 if is_landscape else 38)
        draw.text((cx, cy - int(height * 0.12)), "UP NEXT", font=eyebrow,
                  fill=(*_CARD_ACCENT, 255), anchor="ma")
        rule_w = int(width * 0.06)
        draw.rectangle([cx - rule_w, cy - int(height * 0.12) + eyebrow.size + 22,
                        cx + rule_w, cy - int(height * 0.12) + eyebrow.size + 26],
                       fill=(*_CARD_ACCENT2, 200))
        headline = label or ""
        hfont, headline_lines = _fit_wrapped_text(
            draw,
            headline,
            FONT_BOLD,
            56 if is_landscape else 48,
            int(width * (0.82 if is_landscape else 0.84)),
            max_lines=3 if is_landscape else 4,
            min_px=26,
        )
        draw.multiline_text(
            (cx, cy + int(height * 0.04)),
            "\n".join(headline_lines),
            font=hfont,
            fill=(255, 255, 255, 255),
            anchor="mm",
            align="center",
            spacing=max(8, int(hfont.size * 0.24)),
        )

    else:  # outro
        f1 = _font(FONT_BOLD, 84 if is_landscape else 72)
        f2 = _font(FONT_REGULAR, 32 if is_landscape else 34)
        f3 = _font(FONT_BOLD, 26 if is_landscape else 28)
        draw.text((cx, cy - int(f1.size * 1.2)), "THE CONTEXT WINDOW", font=_fit_text(
            draw, "THE CONTEXT WINDOW", FONT_BOLD, f1.size, int(width * 0.9)),
            fill=(255, 255, 255, 255), anchor="ma")
        draw.text((cx, cy - 18), "New episodes every morning", font=f2,
                  fill=(*MUTED_TEXT, 255), anchor="ma")
        youtube = f"SUBSCRIBE  {YOUTUBE_OUTRO_URL}"
        spotify = f"FOLLOW  {SPOTIFY_OUTRO_URL}"
        youtube_font = _fit_text(
            draw, youtube, FONT_BOLD, f3.size, int(width * 0.88), min_px=20
        )
        spotify_font = _fit_text(
            draw, spotify, FONT_BOLD, f3.size, int(width * 0.88), min_px=20
        )
        draw.text((cx, cy + f2.size + 24), youtube, font=youtube_font,
                  fill=(*_CARD_ACCENT, 245), anchor="ma")
        draw.text((cx, cy + f2.size + 72), spotify, font=spotify_font,
                  fill=(*_CARD_ACCENT2, 245), anchor="ma")
        site_font = _font(FONT_REGULAR, 23 if is_landscape else 25)
        draw.text((cx, cy + f2.size + 126), "contextwindow.distomostech.com",
                  font=site_font, fill=(*MUTED_TEXT, 235), anchor="ma")

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _render_clip_cta_card(platform: str, size: tuple[int, int] = PORTRAIT) -> Image.Image:
    """Render the brief, platform-aware end card used on short-form clips."""
    width, height = size
    img = _card_background(size).copy()
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = width // 2, height // 2

    eyebrow = _font(FONT_BOLD, 38 if width < height else 32)
    headline = _font(FONT_BOLD, 88 if width < height else 72)
    detail = _font(FONT_BOLD, 38 if width < height else 30)
    small = _font(FONT_REGULAR, 27 if width < height else 23)

    draw.text((cx, cy - 230), "THE CONTEXT WINDOW", font=eyebrow,
              fill=(*MUTED_TEXT, 255), anchor="ma")
    if platform == "youtube":
        draw.text((cx, cy - 86), "SUBSCRIBE", font=headline,
                  fill=(255, 255, 255, 255), anchor="ma")
        draw.text((cx, cy + 38), "ON YOUTUBE", font=detail,
                  fill=(*_CARD_ACCENT, 255), anchor="ma")
        destination = "@TheContextWindow-q1z"
    else:
        draw.text((cx, cy - 86), "FOLLOW FOR MORE", font=_fit_text(
            draw, "FOLLOW FOR MORE", FONT_BOLD, headline.size, int(width * 0.88), 52
        ), fill=(255, 255, 255, 255), anchor="ma")
        draw.text((cx, cy + 38), "DAILY AI NEWS", font=detail,
                  fill=(*_CARD_ACCENT2, 255), anchor="ma")
        destination = "Full episodes on YouTube + Spotify"

    draw.text((cx, cy + 135), destination, font=small,
              fill=(*MUTED_TEXT, 255), anchor="ma")
    draw.text((cx, cy + 205), "contextwindow.distomostech.com", font=small,
              fill=(*MUTED_TEXT, 220), anchor="ma")
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _transition_clip(kind: str, size: tuple[int, int], duration: float,
                     label: str | None = None):
    key = (kind, size, label)
    if key not in _CARD_CACHE:
        _CARD_CACHE[key] = np.asarray(_render_transition_card(kind, size, label))
    return ImageClip(_CARD_CACHE[key]).with_duration(max(duration, 0.2))


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

    # The video timeline must mirror pipeline.audio.assemble_episode
    # EXACTLY: intro sting -> lines with pauses -> stinger at segment
    # boundaries -> outro sting. Transition cards cover the stings.
    from pipeline.audio import (
        INTRO_OVERLAP,
        OUTRO_OVERLAP,
        PAUSE_BETWEEN_LINES,
        PAUSE_WITHIN_SPEAKER,
        SEG_OVERLAP,
        TAIL_SILENCE,
        _chapter_title,
        sting_durations_ms,
    )

    stings = sting_durations_ms()
    clips = []
    topic_map = _topic_by_index(script)
    prev_speaker = None
    prev_key = None  # (segment_type, topic) — mirror of audio assembly

    # Track who is speaking when, so the waveform can wear their color
    speaker_windows: dict[str, list[list[float]]] = {}
    cursor = 0.0

    # Intro title card — holds until the first words start (the music's
    # crossfade tail plays under the first speaker's frame)
    intro_s = max(stings["intro"] - INTRO_OVERLAP, 500) / 1000.0
    clips.append(_transition_clip("intro", size, intro_s))
    cursor += intro_s

    for entry in audio_manifest:
        duration = _estimate_duration(entry["audio_path"])
        speaker = entry["speaker"]
        text = entry["text"]
        segment_type = entry.get("segment_type")
        seg_key = (segment_type, entry.get("topic"))

        # Same pause rules as pipeline.audio.assemble_episode
        if prev_key is not None and seg_key != prev_key:
            # Segment boundary: the UP NEXT card holds for the segue's
            # un-overlapped middle (its crossfaded ends play under the
            # outgoing and incoming speaker frames)
            label = _chapter_title(segment_type, entry.get("topic"))
            card_s = max(stings["stinger"] - 2 * SEG_OVERLAP, 500) / 1000.0
            clips.append(_transition_clip("upnext", size, card_s, label=label))
            cursor += card_s
            pause_ms = 0
        elif prev_speaker is not None and speaker != prev_speaker:
            pause_ms = PAUSE_BETWEEN_LINES
        elif prev_speaker is not None:
            pause_ms = PAUSE_WITHIN_SPEAKER
        else:
            pause_ms = 0  # first line — the intro card covers its lead-in

        entry_s = duration + pause_ms / 1000.0
        clips.extend(
            _create_speaker_frames(
                speaker,
                text,
                entry_s,
                size,
                topic=topic_map.get(entry.get("index")),
                speech_duration=duration,
            )
        )
        # Extend this speaker's window (merge back-to-back turns)
        wins = speaker_windows.setdefault(speaker, [])
        if wins and abs(wins[-1][1] - cursor) < 0.05:
            wins[-1][1] = cursor + entry_s
        else:
            wins.append([cursor, cursor + entry_s])
        cursor += entry_s
        prev_speaker = speaker
        prev_key = seg_key

    # Outro card over the outro sting + tail silence
    # Outro card appears once the words end; the outro music's fade-in
    # already played under the final speaker frame
    outro_s = max(stings["outro"] - OUTRO_OVERLAP + TAIL_SILENCE, 500) / 1000.0
    clips.append(_transition_clip("outro", size, outro_s))

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
        fps=ANIMATION_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        logger="bar",
    )

    video.close()
    audio.close()

    if size == LANDSCAPE:
        _overlay_waveform(output_path, speaker_windows)

    logger.info(f"Video saved: {output_path}")
    return output_path


def _ffmpeg_bin() -> str | None:
    import os
    import shutil

    return os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg")


def _overlay_waveform(
    video_path: Path,
    speaker_windows: dict[str, list[list[float]]] | None = None,
    size: tuple[int, int] = LANDSCAPE,
) -> None:
    """
    Composite an audio-reactive waveform along the bottom of the frame:
    a soft glow layer under a crisp line, colored to match whoever is
    speaking (via per-speaker enable windows). Falls back to a single
    neutral wave when no windows are provided. Non-fatal on any failure.
    """
    import subprocess

    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        logger.warning("ffmpeg not found — skipping waveform overlay")
        return

    tmp_path = video_path.with_name(video_path.stem + "_wave.mp4")
    width, height = size
    is_portrait = height > width
    wave_h = 190 if is_portrait else 150
    bottom_margin = 150 if is_portrait else 100
    wave_gain = 6 if is_portrait else 1
    y = f"main_h-{wave_h}-{bottom_margin}"

    def _hex(speaker: str) -> str:
        r, g, b = config.SPEAKERS.get(speaker, config.SPEAKERS["ChatGPT"])["color"]
        return f"0x{r:02X}{g:02X}{b:02X}"

    # One (glow + line) pair per speaker, shown only during their turns
    layers: list[tuple[str, str | None]] = []
    if speaker_windows:
        for speaker, wins in speaker_windows.items():
            if not wins:
                continue
            expr = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in wins)
            layers.append((_hex(speaker), expr))
    if not layers:
        layers = [("0x9EA0B8", None)]

    # Pad the base video's fractional final second, then lift to 24fps so the
    # waveform remains smooth through the last spoken word.
    parts = ["[0:v]tpad=stop_mode=clone:stop_duration=1,fps=24[vb]"]
    last = "[vb]"
    for i, (color, enable) in enumerate(layers):
        en = f":enable='{enable}'" if enable else ""
        parts.append(
            f"[0:a]volume={wave_gain},showwaves=s={width}x{wave_h}:mode=cline:rate=24:scale=sqrt:colors={color}[sw{i}];"
            f"[sw{i}]colorkey=0x000000:0.12:0.2,format=rgba[k{i}];"
            f"[k{i}]split[k{i}a][k{i}b];"
            f"[k{i}a]gblur=sigma=18,colorchannelmixer=aa=0.55[glow{i}];"
            f"[k{i}b]colorchannelmixer=aa=0.85[line{i}]"
        )
        parts.append(f"{last}[glow{i}]overlay=0:{y}:shortest=1{en}[g{i}]")
        parts.append(f"[g{i}][line{i}]overlay=0:{y}:shortest=1{en}[o{i}]")
        last = f"[o{i}]"

    filter_complex = ";".join(parts)
    try:
        subprocess.run(
            [
                ffmpeg, "-y", "-i", str(video_path),
                "-filter_complex", filter_complex,
                "-map", last, "-map", "0:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-c:a", "copy",
                str(tmp_path),
            ],
            check=True, capture_output=True, timeout=2400,
        )
        tmp_path.replace(video_path)
        logger.info(f"Waveform overlay applied ({len(layers)} speaker layer(s))")
    except Exception as e:
        detail = getattr(e, "stderr", b"")
        if isinstance(detail, bytes):
            detail = detail.decode(errors="ignore")[-400:]
        logger.warning(f"Waveform overlay failed (keeping original): {e} {detail}")
        tmp_path.unlink(missing_ok=True)


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
