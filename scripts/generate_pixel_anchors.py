"""Generate the deterministic pixel-anchor portraits used by the video renderer."""

from pathlib import Path

from PIL import Image, ImageDraw


CANVAS = 64
SCALE = 8
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "pixel_anchors"


PALETTES = {
    "claude": {
        "accent": "#CC7832",
        "accent_dark": "#70401F",
        "metal": "#E8D5BF",
        "metal_dark": "#8D7563",
        "screen": "#2B211D",
        "jacket": "#55382B",
    },
    "chatgpt": {
        "accent": "#10A37F",
        "accent_dark": "#075746",
        "metal": "#D9EAE5",
        "metal_dark": "#6E8C83",
        "screen": "#102A25",
        "jacket": "#17483C",
    },
    "gemini": {
        "accent": "#4285F4",
        "accent_dark": "#204E9B",
        "metal": "#DAE5F7",
        "metal_dark": "#71839F",
        "screen": "#14243D",
        "jacket": "#243F6B",
    },
    "grok": {
        "accent": "#EF4444",
        "accent_dark": "#842525",
        "metal": "#E8DADC",
        "metal_dark": "#8F7075",
        "screen": "#2D171A",
        "jacket": "#57262D",
    },
}


def _rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str) -> None:
    draw.rectangle(box, fill=fill)


def _portrait(name: str, palette: dict[str, str]) -> Image.Image:
    """Draw one 64px robotic news anchor, then scale it without smoothing."""
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Broadcast halo and shoulders.
    _rect(draw, (13, 10, 50, 12), palette["accent_dark"])
    _rect(draw, (9, 14, 54, 43), palette["accent_dark"])
    _rect(draw, (6, 20, 57, 36), palette["accent_dark"])
    _rect(draw, (4, 25, 59, 31), palette["accent_dark"])
    _rect(draw, (8, 53, 55, 60), palette["jacket"])
    _rect(draw, (13, 48, 50, 62), palette["jacket"])
    _rect(draw, (20, 45, 43, 63), palette["jacket"])

    # Neck, head casing, ears, and face screen.
    _rect(draw, (27, 43, 36, 51), palette["metal_dark"])
    _rect(draw, (18, 14, 45, 43), palette["metal_dark"])
    _rect(draw, (15, 20, 48, 37), palette["metal_dark"])
    _rect(draw, (13, 24, 17, 33), palette["accent"])
    _rect(draw, (46, 24, 50, 33), palette["accent"])
    _rect(draw, (20, 12, 43, 15), palette["metal"])
    _rect(draw, (18, 17, 45, 38), palette["metal"])
    _rect(draw, (21, 20, 42, 36), palette["screen"])

    # Expressive LED eyes and a calm on-air mouth line.
    _rect(draw, (24, 25, 28, 27), palette["accent"])
    _rect(draw, (35, 25, 39, 27), palette["accent"])
    _rect(draw, (28, 33, 35, 34), palette["metal_dark"])

    # Suit lapels and illuminated tie/core.
    _rect(draw, (19, 50, 25, 59), palette["accent_dark"])
    _rect(draw, (38, 50, 44, 59), palette["accent_dark"])
    _rect(draw, (29, 48, 34, 58), palette["metal"])
    _rect(draw, (30, 52, 33, 59), palette["accent"])

    # Each anchor gets a distinct broadcast silhouette.
    if name == "claude":
        _rect(draw, (16, 11, 22, 17), palette["accent"])
        _rect(draw, (41, 11, 47, 17), palette["accent"])
        _rect(draw, (10, 27, 13, 30), palette["metal"])
    elif name == "chatgpt":
        _rect(draw, (27, 8, 36, 12), palette["accent"])
        _rect(draw, (30, 5, 33, 9), palette["accent"])
        _rect(draw, (50, 27, 54, 29), palette["metal"])
        _rect(draw, (53, 28, 55, 38), palette["accent"])
    elif name == "gemini":
        _rect(draw, (16, 9, 19, 17), palette["accent"])
        _rect(draw, (44, 9, 47, 17), palette["accent"])
        _rect(draw, (12, 19, 15, 22), palette["metal"])
        _rect(draw, (48, 19, 51, 22), palette["metal"])
    else:  # Grok
        _rect(draw, (12, 13, 20, 17), palette["accent"])
        _rect(draw, (43, 13, 51, 17), palette["accent"])
        _rect(draw, (23, 23, 29, 24), palette["accent"])
        _rect(draw, (34, 23, 40, 24), palette["accent"])

    return img.resize((CANVAS * SCALE, CANVAS * SCALE), Image.Resampling.NEAREST)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, palette in PALETTES.items():
        _portrait(name, palette).save(OUTPUT_DIR / f"{name}.png", optimize=True)


if __name__ == "__main__":
    main()
