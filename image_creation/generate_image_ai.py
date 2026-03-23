import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from config import novita

TOPIC_FILE = "../generated_articles/topic_generation/latest_topic.json"
OUTPUT_BASE_DIR = Path("../image_creation")

# Novita documented async endpoint for Flux 2 Dev
CREATE_TASK_URL = "https://api.novita.ai/v3/async/flux-2-dev"
TASK_RESULT_URL = "https://api.novita.ai/v3/async/task-result"

# Generation settings
DEFAULT_SIZE = "1280*720"   # Novita async image APIs use width*height format
DEFAULT_SEED = -1
POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 180

# One fixed prompt pair for stable testing
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


def load_json_file(file_path: str) -> Optional[dict]:
    if not os.path.exists(file_path):
        print(f"Файл не найден: {file_path}")
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка чтения JSON {file_path}: {e}")
        return None


def sanitize_slug(value: str) -> str:
    value = (value or "").strip().lower()
    allowed = []

    for ch in value:
        if ch.isalnum() or ch in "-_":
            allowed.append(ch)
        elif ch == " ":
            allowed.append("-")

    cleaned = "".join(allowed)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")

    cleaned = cleaned.strip("-_")
    return cleaned or "untitled"


def ensure_run_dir(slug: str) -> Path:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = OUTPUT_BASE_DIR / f"{now_str}_{sanitize_slug(slug)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_text_file(file_path: Path, content: str) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


def save_json_file(file_path: Path, payload: dict) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def download_file(url: str, output_path: Path) -> None:
    response = requests.get(url, timeout=180)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)


def get_topic_context(topic_payload: dict) -> dict:
    topic_data = topic_payload.get("topic_data") or {}

    return {
        "title_candidate": (topic_data.get("title_candidate") or "").strip(),
        "slug_candidate": (topic_data.get("slug_candidate") or "").strip(),
        "primary_keyword": (topic_data.get("primary_keyword") or "").strip(),
    }


def build_request_payload(prompt: str, size: str, seed: int) -> dict:
    """
    Flux 2 Dev documented request body includes prompt, size, seed,
    and optionally images / loras. We keep it minimal for text-to-image.
    """
    return {
        "prompt": prompt,
        "size": size,
        "seed": seed,
    }


def get_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def create_generation_task(api_key: str, request_payload: dict) -> Optional[dict]:
    try:
        response = requests.post(
            CREATE_TASK_URL,
            headers=get_headers(api_key),
            json=request_payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        print(f"HTTP ошибка при создании task: {e}")
        try:
            print(response.text)
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"Ошибка при создании task: {e}")
        return None


def get_task_result(api_key: str, task_id: str) -> Optional[dict]:
    try:
        response = requests.get(
            TASK_RESULT_URL,
            headers=get_headers(api_key),
            params={"task_id": task_id},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        print(f"HTTP ошибка при получении результата task: {e}")
        try:
            print(response.text)
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"Ошибка при получении результата task: {e}")
        return None


def poll_until_done(api_key: str, task_id: str, timeout_seconds: int = POLL_TIMEOUT_SECONDS) -> Optional[dict]:
    started_at = time.time()

    while True:
        if time.time() - started_at > timeout_seconds:
            print("Таймаут ожидания результата генерации.")
            return None

        result = get_task_result(api_key, task_id)
        if result is None:
            return None

        task = result.get("task", {})
        status = task.get("status", "")

        print(f"Task status: {status}")

        if status == "TASK_STATUS_SUCCEED":
            return result

        if status == "TASK_STATUS_FAILED":
            reason = task.get("reason", "")
            print(f"Генерация завершилась с ошибкой. Reason: {reason}")
            return result

        time.sleep(POLL_INTERVAL_SECONDS)


def save_images_from_result(result: dict, run_dir: Path) -> list[str]:
    images = result.get("images", []) or []
    saved_images = []

    for i, image_info in enumerate(images, start=1):
        image_url = image_info.get("image_url")
        if not image_url:
            continue

        image_type = image_info.get("image_type", "jpeg").lower()
        if image_type not in {"jpeg", "jpg", "png", "webp"}:
            image_type = "jpg"

        extension = "jpg" if image_type == "jpeg" else image_type
        output_path = run_dir / f"image_{i}.{extension}"

        download_file(image_url, output_path)
        saved_images.append(str(output_path).replace("\\", "/"))

    return saved_images


def generate_cover_background() -> Optional[dict]:
    topic_payload = load_json_file(TOPIC_FILE)
    if topic_payload is None:
        print("Не удалось загрузить latest_topic.json.")
        return None

    topic_meta = get_topic_context(topic_payload)
    slug = topic_meta.get("slug_candidate") or "untitled"

    api_key = str(novita.get("api_key", "")).strip()
    model_name = str(novita.get("image_model", "")).strip()

    if not api_key:
        print("В config.novita отсутствует api_key.")
        return None

    if not model_name:
        print("В config.novita отсутствует image_model.")
        return None

    run_dir = ensure_run_dir(slug)
    OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

    # Since flux-2-dev docs expose only prompt/size/seed clearly,
    # we bake anti-text guidance into one merged prompt.
    merged_prompt = f"{POSITIVE_PROMPT} Avoid any text, letters, words, logos, captions, readable interface text. Negative constraints: {NEGATIVE_PROMPT}"

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
        "notes": {
            "purpose": "raw cover background generation for article covers",
            "topic_used_in_prompt": False,
            "business_theme": True,
            "text_forbidden": True,
            "soft_silhouettes_allowed": True,
            "laptops_allowed": True,
        },
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
        print("Не удалось создать task генерации.")
        return None

    save_json_file(run_dir / "task_create_response.json", task_create_response)

    task_id = task_create_response.get("task_id")
    if not task_id:
        print("В ответе нет task_id.")
        print(json.dumps(task_create_response, ensure_ascii=False, indent=2))
        return None

    print(f"Создан task_id: {task_id}")

    final_result = poll_until_done(api_key, task_id)
    if final_result is None:
        print("Не удалось получить финальный результат task.")
        return None

    save_json_file(run_dir / "response.json", final_result)

    task_status = (final_result.get("task", {}) or {}).get("status", "")
    if task_status != "TASK_STATUS_SUCCEED":
        print("Task не завершился успешно.")
        print(json.dumps(final_result, ensure_ascii=False, indent=2))
        return None

    saved_images = save_images_from_result(final_result, run_dir)
    if not saved_images:
        print("Картинки не были сохранены: images пустой или image_url отсутствует.")
        return None

    return {
        "run_dir": str(run_dir).replace("\\", "/"),
        "positive_prompt_file": str((run_dir / "positive_prompt.txt")).replace("\\", "/"),
        "negative_prompt_file": str((run_dir / "negative_prompt.txt")).replace("\\", "/"),
        "merged_prompt_file": str((run_dir / "merged_prompt.txt")).replace("\\", "/"),
        "request_file": str((run_dir / "request.json")).replace("\\", "/"),
        "task_create_response_file": str((run_dir / "task_create_response.json")).replace("\\", "/"),
        "response_file": str((run_dir / "response.json")).replace("\\", "/"),
        "images": saved_images,
        "topic_context": topic_meta,
        "used_model_from_config": model_name,
        "used_size": DEFAULT_SIZE,
        "used_seed": DEFAULT_SEED,
        "task_id": task_id,
    }


def main():
    result = generate_cover_background()

    if result is None:
        print("Генерация cover background не удалась.")
        return

    print("Cover background успешно сгенерирован и сохранен.")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()