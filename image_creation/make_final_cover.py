import json
import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

TOPIC_FILE = Path("../generated_articles/topic_generation/latest_topic.json")
IMAGE_CREATION_DIR = Path("../image_creation")
LOGO_FILE = Path("crino_logo/logo_1_variant.png")

OUTPUT_FILENAME = "final_cover.webp"

FINAL_WIDTH = 2400
FINAL_HEIGHT = 1256

# Затемнение фона
DARK_OVERLAY_OPACITY = 0.10

# Логотип
LOGO_MAX_WIDTH = 220
LOGO_TOP_MARGIN = 150

# Заголовок
TITLE_MAX_WIDTH_RATIO = 0.3
TITLE_COLOR = (255, 255, 255, 255)
TITLE_CENTER_Y_RATIO = 0.60
TITLE_LINE_SPACING = 30

# Подложка под текст
TITLE_BOX_HORIZONTAL_PADDING = 50
TITLE_BOX_VERTICAL_PADDING = 35
TITLE_BOX_RADIUS = 26
TITLE_BOX_FILL = (0, 0, 0, 50)

# Настройки WebP
# 80-86 обычно дает очень хороший баланс.
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


def load_json_file(file_path: Path) -> Optional[dict]:
    if not file_path.exists():
        print(f"Файл не найден: {file_path}")
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка чтения JSON {file_path}: {e}")
        return None


def get_latest_run_dir(base_dir: Path) -> Optional[Path]:
    if not base_dir.exists():
        print(f"Папка не найдена: {base_dir}")
        return None

    subdirs = [p for p in base_dir.iterdir() if p.is_dir()]
    if not subdirs:
        print(f"В папке {base_dir} нет подпапок.")
        return None

    return max(subdirs, key=lambda p: p.stat().st_mtime)


def find_generated_image(run_dir: Path) -> Optional[Path]:
    preferred_names = [
        "image_1.png",
        "image_1.jpg",
        "image_1.jpeg",
        "image_1.webp",
    ]

    for name in preferred_names:
        path = run_dir / name
        if path.exists():
            return path

    candidates = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        candidates.extend(run_dir.glob(ext))

    if not candidates:
        print(f"В папке {run_dir} не найдено ни одной картинки.")
        return None

    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def get_article_title(topic_payload: dict) -> str:
    topic_data = topic_payload.get("topic_data") or {}

    title = (topic_data.get("title_candidate") or "").strip()
    if title:
        return title

    slug = (topic_data.get("slug_candidate") or "").strip()
    if slug:
        return slug.replace("-", " ").replace("_", " ").title()

    return "Untitled Article"


def pick_font_path() -> Optional[str]:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def open_rgba(image_path: Path) -> Image.Image:
    return Image.open(image_path).convert("RGBA")


def resize_cover(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
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
    right = left + target_width
    bottom = top + target_height

    return resized.crop((left, top, right, bottom))


def apply_dark_overlay(base: Image.Image, opacity: float) -> Image.Image:
    alpha = max(0, min(255, int(255 * opacity)))
    overlay = Image.new("RGBA", base.size, (0, 0, 0, alpha))
    return Image.alpha_composite(base, overlay)


def paste_logo(canvas: Image.Image, logo_path: Path) -> None:
    if not logo_path.exists():
        print(f"Логотип не найден: {logo_path}")
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


def draw_title_box(
    canvas: Image.Image,
    x: int,
    y: int,
    text_width: int,
    text_height: int,
) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")

    left = x - TITLE_BOX_HORIZONTAL_PADDING
    top = y - TITLE_BOX_VERTICAL_PADDING
    right = x + text_width + TITLE_BOX_HORIZONTAL_PADDING
    bottom = y + text_height + TITLE_BOX_VERTICAL_PADDING

    draw.rounded_rectangle(
        [(left, top), (right, bottom)],
        radius=TITLE_BOX_RADIUS,
        fill=TITLE_BOX_FILL,
    )


def measure_multiline_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    spacing: int,
):
    bbox = draw.multiline_textbbox(
        (0, 0),
        text,
        font=font,
        spacing=spacing,
        align="center",
    )
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return width, height, bbox


def wrap_title_by_width(
    draw: ImageDraw.ImageDraw,
    title: str,
    font,
    max_width: int,
) -> str:
    words = title.split()
    if not words:
        return title

    current_lines = []
    current_line = words[0]

    for word in words[1:]:
        test_line = f"{current_line} {word}"
        bbox = draw.textbbox((0, 0), test_line, font=font)
        line_width = bbox[2] - bbox[0]

        if line_width <= max_width:
            current_line = test_line
        else:
            current_lines.append(current_line)
            current_line = word

    current_lines.append(current_line)
    return "\n".join(current_lines)


def fit_title_text(draw: ImageDraw.ImageDraw, title: str, canvas_width: int):
    font_path = pick_font_path()
    max_text_width = int(canvas_width * TITLE_MAX_WIDTH_RATIO)

    for font_size in range(150, 55, -2):
        if font_path:
            font = ImageFont.truetype(font_path, font_size)
        else:
            font = ImageFont.load_default()

        wrapped = wrap_title_by_width(draw, title, font, max_text_width)
        text_width, text_height, _ = measure_multiline_text(
            draw=draw,
            text=wrapped,
            font=font,
            spacing=TITLE_LINE_SPACING,
        )

        max_allowed_height = int(FINAL_HEIGHT * 0.35)
        if text_width <= max_text_width and text_height <= max_allowed_height:
            return wrapped, font, text_width, text_height

    if font_path:
        fallback_font = ImageFont.truetype(font_path, 60)
    else:
        fallback_font = ImageFont.load_default()

    wrapped = textwrap.fill(title, width=18)
    text_width, text_height, _ = measure_multiline_text(
        draw=draw,
        text=wrapped,
        font=fallback_font,
        spacing=TITLE_LINE_SPACING,
    )
    return wrapped, fallback_font, text_width, text_height


def draw_title(canvas: Image.Image, title: str) -> None:
    draw = ImageDraw.Draw(canvas)

    wrapped_title, font, text_width, text_height = fit_title_text(
        draw=draw,
        title=title,
        canvas_width=canvas.width,
    )

    x = (canvas.width - text_width) // 2
    y = int(canvas.height * TITLE_CENTER_Y_RATIO - text_height / 2)

    draw_title_box(
        canvas=canvas,
        x=x,
        y=y,
        text_width=text_width,
        text_height=text_height,
    )

    draw.multiline_text(
        (x, y),
        wrapped_title,
        font=font,
        fill=TITLE_COLOR,
        align="center",
        spacing=TITLE_LINE_SPACING,
    )


def cleanup_old_outputs(run_dir: Path) -> None:
    old_files = [
        run_dir / "final_cover.png",
        run_dir / "final_cover.jpg",
        run_dir / "final_cover.jpeg",
        run_dir / "final_cover.webp",
    ]

    for file_path in old_files:
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                print(f"Не удалось удалить старый файл {file_path}: {e}")


def save_final_cover_webp(image: Image.Image, output_path: Path) -> None:
    # WebP лучше сохранять из RGB, если прозрачность в финале не нужна
    image_rgb = image.convert("RGB")

    image_rgb.save(
        output_path,
        format="WEBP",
        quality=WEBP_QUALITY,
        method=WEBP_METHOD,
        optimize=True,
    )


def create_final_cover():
    latest_dir = get_latest_run_dir(IMAGE_CREATION_DIR)
    if latest_dir is None:
        return None

    print(f"Найдена последняя папка: {latest_dir}")

    source_image_path = find_generated_image(latest_dir)
    if source_image_path is None:
        return None

    print(f"Найдена исходная картинка: {source_image_path}")

    topic_payload = load_json_file(TOPIC_FILE)
    if topic_payload is None:
        return None

    title = get_article_title(topic_payload)
    print(f"Заголовок статьи: {title}")

    background = open_rgba(source_image_path)
    background = resize_cover(background, FINAL_WIDTH, FINAL_HEIGHT)
    background = apply_dark_overlay(background, DARK_OVERLAY_OPACITY)

    paste_logo(background, LOGO_FILE)
    draw_title(background, title)

    cleanup_old_outputs(latest_dir)

    output_path = latest_dir / OUTPUT_FILENAME
    save_final_cover_webp(background, output_path)

    try:
        file_size_kb = round(output_path.stat().st_size / 1024, 2)
    except Exception:
        file_size_kb = None

    result = {
        "latest_dir": str(latest_dir).replace("\\", "/"),
        "source_image": str(source_image_path).replace("\\", "/"),
        "output_image": str(output_path).replace("\\", "/"),
        "title": title,
        "size": f"{FINAL_WIDTH}x{FINAL_HEIGHT}",
        "dark_overlay_opacity": DARK_OVERLAY_OPACITY,
        "logo_file": str(LOGO_FILE).replace("\\", "/"),
        "output_format": "WEBP",
        "webp_quality": WEBP_QUALITY,
        "webp_method": WEBP_METHOD,
        "file_size_kb": file_size_kb,
    }

    print("Финальный cover создан:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    create_final_cover()


if __name__ == "__main__":
    main()