from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


LOGO_FILE = Path("image_creation/crino_logo/logo_1_variant.png")
OUTPUT_WEBP_FILENAME = "final_cover.webp"
OUTPUT_PNG_FILENAME = "final_cover.png"
FINAL_WIDTH = 2400
FINAL_HEIGHT = 1256
DARK_OVERLAY_OPACITY = 0.10
LOGO_MAX_WIDTH = 220
LOGO_TOP_MARGIN = 150
TITLE_MAX_WIDTH_RATIO = 0.3
TITLE_COLOR = (255, 255, 255, 255)
TITLE_CENTER_Y_RATIO = 0.60
TITLE_LINE_SPACING = 30
TITLE_BOX_HORIZONTAL_PADDING = 50
TITLE_BOX_VERTICAL_PADDING = 35
TITLE_BOX_RADIUS = 26
TITLE_BOX_FILL = (0, 0, 0, 50)
WEBP_QUALITY = 84
WEBP_METHOD = 6

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def pick_font_path() -> Optional[str]:
    """Return the first available font path from the candidate list."""
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def open_rgba(image_path: Path) -> Image.Image:
    """Open an image as RGBA."""
    return Image.open(image_path).convert("RGBA")


def resize_cover(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Resize and crop an image to cover the target canvas size."""
    src_w, src_h = image.size
    src_ratio = src_w / src_h
    target_ratio = target_width / target_height
    if src_ratio > target_ratio:
        new_h = target_height
        new_w = int(new_h * src_ratio)
    else:
        new_w = target_width
        new_h = int(new_w / src_ratio)
    resized = image.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_width) // 2
    top = (new_h - target_height) // 2
    return resized.crop((left, top, left + target_width, top + target_height))


def apply_dark_overlay(base: Image.Image, opacity: float) -> Image.Image:
    """Apply a semi-transparent dark overlay on top of the background."""
    alpha = max(0, min(255, int(255 * opacity)))
    overlay = Image.new("RGBA", base.size, (0, 0, 0, alpha))
    return Image.alpha_composite(base, overlay)


def paste_logo(canvas: Image.Image, logo_path: Path) -> None:
    """Place the project logo at the top center of the cover."""
    if not logo_path.exists():
        print(f"Logo file not found: {logo_path}")
        return
    logo = open_rgba(logo_path)
    logo_w, logo_h = logo.size
    scale = min(0.6, LOGO_MAX_WIDTH / logo_w)
    new_w = int(logo_w * scale)
    new_h = int(logo_h * scale)
    logo = logo.resize((new_w, new_h), Image.LANCZOS)
    x = (canvas.width - new_w) // 2
    y = LOGO_TOP_MARGIN
    canvas.alpha_composite(logo, (x, y))


def draw_title_box(canvas: Image.Image, x: int, y: int, text_width: int, text_height: int) -> None:
    """Draw the rounded rectangle behind the title text."""
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle(
        [
            (x - TITLE_BOX_HORIZONTAL_PADDING, y - TITLE_BOX_VERTICAL_PADDING),
            (x + text_width + TITLE_BOX_HORIZONTAL_PADDING, y + text_height + TITLE_BOX_VERTICAL_PADDING),
        ],
        radius=TITLE_BOX_RADIUS,
        fill=TITLE_BOX_FILL,
    )


def measure_multiline_text(draw: ImageDraw.ImageDraw, text: str, font, spacing: int):
    """Measure a multiline text block."""
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align="center")
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox


def wrap_title_by_width(draw: ImageDraw.ImageDraw, title: str, font, max_width: int) -> str:
    """Wrap a title so each line fits the configured width."""
    words = title.split()
    if not words:
        return title
    current_lines: list[str] = []
    current_line = words[0]
    for word in words[1:]:
        test_line = f"{current_line} {word}"
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            current_lines.append(current_line)
            current_line = word
    current_lines.append(current_line)
    return "\n".join(current_lines)


def fit_title_text(draw: ImageDraw.ImageDraw, title: str, canvas_width: int):
    """Pick a font size that fits the configured title area."""
    font_path = pick_font_path()
    max_text_width = int(canvas_width * TITLE_MAX_WIDTH_RATIO)
    for font_size in range(150, 55, -2):
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        wrapped = wrap_title_by_width(draw, title, font, max_text_width)
        text_width, text_height, _ = measure_multiline_text(draw, wrapped, font, TITLE_LINE_SPACING)
        if text_width <= max_text_width and text_height <= int(FINAL_HEIGHT * 0.35):
            return wrapped, font, text_width, text_height
    fallback_font = ImageFont.truetype(font_path, 60) if font_path else ImageFont.load_default()
    wrapped = textwrap.fill(title, width=18)
    text_width, text_height, _ = measure_multiline_text(draw, wrapped, fallback_font, TITLE_LINE_SPACING)
    return wrapped, fallback_font, text_width, text_height


def draw_title(canvas: Image.Image, title: str) -> None:
    """Render the article title on the cover."""
    draw = ImageDraw.Draw(canvas)
    wrapped_title, font, text_width, text_height = fit_title_text(draw, title, canvas.width)
    x = (canvas.width - text_width) // 2
    y = int(canvas.height * TITLE_CENTER_Y_RATIO - text_height / 2)
    draw_title_box(canvas, x, y, text_width, text_height)
    draw.multiline_text((x, y), wrapped_title, font=font, fill=TITLE_COLOR, align="center", spacing=TITLE_LINE_SPACING)


def save_final_cover_webp(image: Image.Image, output_path: Path) -> None:
    """Save the final cover as an optimized WebP file."""
    image.convert("RGB").save(output_path, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD, optimize=True)


def save_final_cover_png(image: Image.Image, output_path: Path) -> None:
    """Save the final cover as a PNG file."""
    image.convert("RGB").save(output_path, format="PNG", optimize=True)


def create_final_cover(title: str, source_image_path: Path, output_dir: Path) -> dict | None:
    """Create local PNG and WebP cover variants for an article."""
    if not source_image_path.exists():
        print(f"Source image not found: {source_image_path}")
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    background = open_rgba(source_image_path)
    background = resize_cover(background, FINAL_WIDTH, FINAL_HEIGHT)
    background = apply_dark_overlay(background, DARK_OVERLAY_OPACITY)
    paste_logo(background, LOGO_FILE)
    draw_title(background, title)
    webp_output_path = output_dir / OUTPUT_WEBP_FILENAME
    png_output_path = output_dir / OUTPUT_PNG_FILENAME
    save_final_cover_webp(background, webp_output_path)
    save_final_cover_png(background, png_output_path)
    result = {
        "output_webp": str(webp_output_path).replace("\\", "/"),
        "output_png": str(png_output_path).replace("\\", "/"),
        "source_image": str(source_image_path).replace("\\", "/"),
        "title": title,
        "size": f"{FINAL_WIDTH}x{FINAL_HEIGHT}",
        "output_formats": ["webp", "png"],
        "webp_quality": WEBP_QUALITY,
        "webp_method": WEBP_METHOD,
    }
    print("Created the final cover image variants.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result
