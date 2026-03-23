from __future__ import annotations

import json
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

POSITIVE_PROMPT = (
    "Premium business-tech atmosphere, modern professional environment, subtle cinematic composition, "
    "clean spacious scene, elegant lighting, refined depth, sophisticated startup mood, "
    "abstract but not purely geometric, visually rich but restrained, premium editorial quality, "
    "soft silhouettes of professionals allowed, subtle laptops allowed, no dominant central object, "
    "no dramatic action, no busy office scene, no poster design, no ad layout, no headline composition."
)

NEGATIVE_PROMPT = (
    "text, letters, words, numbers, typography, logo, watermark, brand name, signage, title, caption, "
    "readable text, ui labels, dashboard text, analytics text, poster, advertisement, banner, "
    "infographic, webpage mockup, app mockup, giant central object, clutter, crowded meeting room, "
    "sharp tiny details, product ad, brochure style, stock photo handshake, exaggerated geometry"
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
        response = requests.post(CREATE_TASK_URL, headers=get_headers(api_key), json=request_payload, timeout=120)
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


def generate_cover_background(topic_payload: dict, run_dir: Path) -> Optional[dict]:
    """Generate raw background images for an approved topic."""
    topic_data = topic_payload.get("topic_data") or {}
    topic_meta = {
        "title_candidate": str(topic_data.get("title_candidate", "")).strip(),
        "slug_candidate": str(topic_data.get("slug_candidate", "")).strip(),
        "primary_keyword": str(topic_data.get("primary_keyword", "")).strip(),
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
    merged_prompt = (
        f"{POSITIVE_PROMPT} Avoid any text, letters, words, logos, captions, readable interface text. "
        f"Negative constraints: {NEGATIVE_PROMPT}"
    )
    request_payload = build_request_payload(prompt=merged_prompt, size=DEFAULT_SIZE, seed=DEFAULT_SEED)
    local_request_meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "novita",
        "endpoint_url": CREATE_TASK_URL,
        "task_result_url": TASK_RESULT_URL,
        "model_from_config": model_name,
        "topic_context": topic_meta,
        "positive_prompt": POSITIVE_PROMPT,
        "negative_prompt": NEGATIVE_PROMPT,
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
