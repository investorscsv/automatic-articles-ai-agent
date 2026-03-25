from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from config import novita


CREATE_TASK_URL = "https://api.novita.ai/v3/async/flux-2-dev"
TASK_RESULT_URL = "https://api.novita.ai/v3/async/task-result"
DEFAULT_SIZE = "1280*720"
DEFAULT_SEED = -1
POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 180

# Базовый позитивный стиль: уводим модель в реалистичную светлую editorial-фотографию,
# а не в generic dark startup open space.
POSITIVE_PROMPT = (
    "Ultra-realistic editorial photography, bright natural daylight, airy and modern environment, "
    "authentic professional setting, believable materials and textures, premium magazine-quality image, "
    "natural composition, realistic depth of field, contemporary technology atmosphere, "
    "human presence only when relevant, candid and unstaged, visually clean and elegant, "
    "avoid generic startup office look, avoid dark moody interiors."
)

# Здесь прямым текстом запрещаем самые частые нежелательные паттерны.
NEGATIVE_PROMPT = (
    "text, letters, words, numbers, typography, logo, watermark, brand name, signage, title, caption, "
    "readable text, ui labels, dashboard text, analytics text, poster, advertisement, banner, "
    "infographic, webpage mockup, app mockup, giant central object, clutter, crowded meeting room, "
    "sharp tiny details, product ad, brochure style, stock photo handshake, exaggerated geometry, "
    "dark room, dim office, gloomy atmosphere, moody blue light, underexposed image, night office, "
    "generic open space, repetitive desks, staged corporate team pose, plastic CGI humans, "
    "overly dramatic cinematic darkness, oversaturated neon lighting"
)

# Несколько направлений сцены, чтобы картинки не были одинаковыми.
SCENE_PRESETS = [
    "bright glass meeting room with natural daylight and realistic reflections",
    "modern workspace near large windows, airy interior, Scandinavian aesthetic",
    "close-up editorial scene with hands, notebook, laptop, coffee, and soft daylight",
    "urban office lounge with warm natural materials and authentic human presence",
    "clean premium home-office setup with realistic atmosphere",
    "creative studio environment with sunlight, depth, and subtle technology details",
    "minimal business environment with elegant furniture, daylight, and calm composition",
]

PHOTO_STYLE_PROMPT = (
    "Shot like premium editorial photography, full-frame camera look, realistic dynamic range, "
    "natural skin tones, soft daylight, believable contrast, authentic textures."
)


def save_text_file(file_path: Path, content: str) -> None:
    """Write plain text to disk."""
    file_path.write_text(content, encoding="utf-8")


def save_json_file(file_path: Path, payload: dict) -> None:
    """Write JSON to disk."""
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def download_file(url: str, output_path: Path) -> None:
    """Download a remote file to disk."""
    response = requests.get(url, timeout=180)
    response.raise_for_status()
    output_path.write_bytes(response.content)


def build_request_payload(prompt: str, size: str, seed: int) -> dict:
    """Build the Novita image-generation payload."""
    return {"prompt": prompt, "size": size, "seed": seed}


def get_headers(api_key: str) -> dict:
    """Build request headers for the Novita API."""
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def create_generation_task(api_key: str, request_payload: dict) -> Optional[dict]:
    """Create an asynchronous Novita image task."""
    try:
        response = requests.post(
            CREATE_TASK_URL,
            headers=get_headers(api_key),
            json=request_payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        print(f"HTTP error while creating the image task: {exc}")
        try:
            print(response.text)
        except Exception:  # noqa: BLE001
            pass
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to create the image task: {exc}")
        return None


def get_task_result(api_key: str, task_id: str) -> Optional[dict]:
    """Fetch a Novita task result."""
    try:
        response = requests.get(
            TASK_RESULT_URL,
            headers=get_headers(api_key),
            params={"task_id": task_id},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        print(f"HTTP error while fetching the task result: {exc}")
        try:
            print(response.text)
        except Exception:  # noqa: BLE001
            pass
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to fetch the task result: {exc}")
        return None


def poll_until_done(api_key: str, task_id: str, timeout_seconds: int = POLL_TIMEOUT_SECONDS) -> Optional[dict]:
    """Poll a Novita image task until it finishes or times out."""
    started_at = time.time()
    while True:
        if time.time() - started_at > timeout_seconds:
            print("Timed out while waiting for image generation.")
            return None

        result = get_task_result(api_key, task_id)
        if result is None:
            return None

        task = result.get("task", {})
        status = task.get("status", "")
        print(f"Image task status: {status}")

        if status == "TASK_STATUS_SUCCEED":
            return result

        if status == "TASK_STATUS_FAILED":
            print(f"Image generation failed. Reason: {task.get('reason', '')}")
            return result

        time.sleep(POLL_INTERVAL_SECONDS)


def save_images_from_result(result: dict, run_dir: Path) -> list[str]:
    """Download all generated images from a Novita result payload."""
    images = result.get("images", []) or []
    saved_images: list[str] = []

    for index, image_info in enumerate(images, start=1):
        image_url = image_info.get("image_url")
        if not image_url:
            continue

        image_type = str(image_info.get("image_type", "jpeg")).lower()
        if image_type not in {"jpeg", "jpg", "png", "webp"}:
            image_type = "jpg"

        extension = "jpg" if image_type == "jpeg" else image_type
        output_path = run_dir / f"image_{index}.{extension}"
        download_file(image_url, output_path)
        saved_images.append(str(output_path).replace("\\", "/"))

    return saved_images


def normalize_topic_value(value: object) -> str:
    """Convert arbitrary topic value to a clean string."""
    return str(value or "").strip()


def pick_scene_preset(slug_candidate: str, primary_keyword: str, title_candidate: str) -> str:
    """
    Pick a scene preset.
    We keep this deterministic enough to avoid chaotic variety,
    but still diverse across topics.
    """
    haystack = f"{slug_candidate} {primary_keyword} {title_candidate}".lower()

    if any(word in haystack for word in ["seo", "marketing", "growth", "traffic", "content"]):
        return "close-up editorial scene with hands, notebook, laptop, coffee, and soft daylight"

    if any(word in haystack for word in ["developer", "engineer", "software", "ai", "agent", "coding"]):
        return "modern workspace near large windows, airy interior, Scandinavian aesthetic"

    if any(word in haystack for word in ["startup", "founder", "saas", "product", "b2b"]):
        return "bright glass meeting room with natural daylight and realistic reflections"

    if any(word in haystack for word in ["remote", "distributed", "freelance", "global"]):
        return "clean premium home-office setup with realistic atmosphere"

    return random.choice(SCENE_PRESETS)


def build_topic_visual_context(topic_meta: dict) -> str:
    """Create a topic-aware visual direction for the generation prompt."""
    title_candidate = normalize_topic_value(topic_meta.get("title_candidate"))
    slug_candidate = normalize_topic_value(topic_meta.get("slug_candidate"))
    primary_keyword = normalize_topic_value(topic_meta.get("primary_keyword"))

    meaningful_parts = [part for part in [title_candidate, primary_keyword, slug_candidate] if part]

    if meaningful_parts:
        joined_context = ". ".join(meaningful_parts)
        return (
            f"Article topic context: {joined_context}. "
            "Create a specific, realistic editorial scene or visual metaphor that matches this topic. "
            "The image should feel authentic, modern, bright, and naturally photographed. "
            "Do not use text, interface labels, dashboards, or obvious poster composition."
        )

    return (
        "Create a realistic, premium editorial business-tech image with bright natural light, "
        "authentic environment, calm composition, and non-generic atmosphere. "
        "Do not use text, interface labels, dashboards, or obvious poster composition."
    )


def build_merged_prompt(topic_meta: dict) -> str:
    """Assemble the final generation prompt."""
    title_candidate = normalize_topic_value(topic_meta.get("title_candidate"))
    slug_candidate = normalize_topic_value(topic_meta.get("slug_candidate"))
    primary_keyword = normalize_topic_value(topic_meta.get("primary_keyword"))

    scene_preset = pick_scene_preset(
        slug_candidate=slug_candidate,
        primary_keyword=primary_keyword,
        title_candidate=title_candidate,
    )

    topic_visual_context = build_topic_visual_context(topic_meta)

    return (
        f"{POSITIVE_PROMPT} "
        f"{PHOTO_STYLE_PROMPT} "
        f"Scene direction: {scene_preset}. "
        f"{topic_visual_context} "
        "Prefer bright daylight, light neutral tones, realistic interiors or real-life work environments, "
        "candid human presence only when relevant, and natural visual balance. "
        "Avoid generic dark open-space offices and avoid repetitive stock-photo compositions. "
        "Avoid any text, letters, words, logos, captions, readable interface text. "
        f"Negative constraints: {NEGATIVE_PROMPT}"
    )


def generate_cover_background(topic_payload: dict, run_dir: Path) -> Optional[dict]:
    """Generate raw background images for an approved topic."""
    topic_data = topic_payload.get("topic_data") or {}
    topic_meta = {
        "title_candidate": normalize_topic_value(topic_data.get("title_candidate")),
        "slug_candidate": normalize_topic_value(topic_data.get("slug_candidate")),
        "primary_keyword": normalize_topic_value(topic_data.get("primary_keyword")),
    }

    api_key = str(novita.get("api_key", "")).strip()
    model_name = str(novita.get("image_model", "")).strip()

    if not api_key:
        print("config.novita.api_key is missing.")
        return None

    if not model_name:
        print("config.novita.image_model is missing.")
        return None

    run_dir.mkdir(parents=True, exist_ok=True)

    merged_prompt = build_merged_prompt(topic_meta)
    request_payload = build_request_payload(
        prompt=merged_prompt,
        size=DEFAULT_SIZE,
        seed=DEFAULT_SEED,
    )

    local_request_meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "novita",
        "endpoint_url": CREATE_TASK_URL,
        "task_result_url": TASK_RESULT_URL,
        "model_from_config": model_name,
        "topic_context": topic_meta,
        "positive_prompt": POSITIVE_PROMPT,
        "negative_prompt": NEGATIVE_PROMPT,
        "photo_style_prompt": PHOTO_STYLE_PROMPT,
        "merged_prompt": merged_prompt,
        "request_payload": request_payload,
    }

    save_text_file(run_dir / "positive_prompt.txt", POSITIVE_PROMPT)
    save_text_file(run_dir / "negative_prompt.txt", NEGATIVE_PROMPT)
    save_text_file(run_dir / "merged_prompt.txt", merged_prompt)
    save_json_file(run_dir / "request.json", local_request_meta)

    task_create_response = create_generation_task(api_key, request_payload)
    if task_create_response is None:
        print("Failed to create the image-generation task.")
        return None

    save_json_file(run_dir / "task_create_response.json", task_create_response)

    task_id = task_create_response.get("task_id")
    if not task_id:
        print("The task creation response does not include task_id.")
        return None

    print(f"Created image task_id: {task_id}")

    final_result = poll_until_done(api_key, task_id)
    if final_result is None:
        print("Failed to fetch the final image-generation result.")
        return None

    save_json_file(run_dir / "response.json", final_result)

    task_status = (final_result.get("task", {}) or {}).get("status", "")
    if task_status != "TASK_STATUS_SUCCEED":
        print("The image task did not complete successfully.")
        return None

    saved_images = save_images_from_result(final_result, run_dir)
    if not saved_images:
        print("No images were saved because the result did not contain downloadable image URLs.")
        return None

    return {
        "run_dir": str(run_dir).replace("\\", "/"),
        "images": saved_images,
        "topic_context": topic_meta,
        "used_model_from_config": model_name,
        "used_size": DEFAULT_SIZE,
        "used_seed": DEFAULT_SEED,
        "task_id": task_id,
    }