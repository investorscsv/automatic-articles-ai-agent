from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from article_generator import generate_article_body, save_article_package, validate_article_body
from article_publisher import publish_article
from existing_articles_service import refresh_existing_articles_snapshot
from image_creation.generate_image_ai import generate_cover_background
from image_creation.make_final_cover import create_final_cover
from topic_generator import generate_new_topic, save_topic_locally


WORKFLOW_DIR = Path("generated_articles/workflow")
WORKFLOW_STATE_FILE = WORKFLOW_DIR / "state.json"
LATEST_TOPIC_FILE = Path("generated_articles/topic_generation/latest_topic.json")


@dataclass
class WorkflowState:
    status: str
    created_at: str
    updated_at: str
    existing_articles_count: int
    snapshot_path: str
    topic_attempts: list[dict]
    approved_topic: dict | None
    seo_data: dict | None
    article: dict | None
    image: dict | None
    publish: dict | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "existing_articles_count": self.existing_articles_count,
            "snapshot_path": self.snapshot_path,
            "topic_attempts": self.topic_attempts,
            "approved_topic": self.approved_topic,
            "seo_data": self.seo_data,
            "article": self.article,
            "image": self.image,
            "publish": self.publish,
        }


def utc_now() -> str:
    """Return the current UTC timestamp as ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def ensure_workflow_dir() -> None:
    """Create the workflow directory when needed."""
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_TOPIC_FILE.parent.mkdir(parents=True, exist_ok=True)


def create_empty_state() -> WorkflowState:
    """Create a new workflow state object."""
    now = utc_now()
    return WorkflowState(
        status="initialized",
        created_at=now,
        updated_at=now,
        existing_articles_count=0,
        snapshot_path="",
        topic_attempts=[],
        approved_topic=None,
        seo_data=None,
        article=None,
        image=None,
        publish=None,
    )


def load_state() -> WorkflowState:
    """Load the persisted workflow state or create a new one."""
    ensure_workflow_dir()
    if not WORKFLOW_STATE_FILE.exists():
        return create_empty_state()
    payload = json.loads(WORKFLOW_STATE_FILE.read_text(encoding="utf-8"))
    return WorkflowState(**payload)


def save_state(state: WorkflowState) -> None:
    """Persist the workflow state to disk."""
    state.updated_at = utc_now()
    WORKFLOW_STATE_FILE.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def reset_dependent_state(state: WorkflowState, *, clear_topic: bool = False) -> None:
    """Reset downstream workflow stages after an upstream change."""
    if clear_topic:
        state.approved_topic = None
        state.topic_attempts = []
    state.seo_data = None
    state.article = None
    state.image = None
    state.publish = None


def prompt_choice(question: str, choices: dict[str, str]) -> str:
    """Prompt the user until a valid short choice is entered."""
    while True:
        print(question)
        for key, description in choices.items():
            print(f"  {key} - {description}")
        answer = input("> ").strip().lower()
        if answer in choices:
            return answer
        print("Invalid choice. Please try again.")


def prompt_yes_no(question: str, default: str = "yes") -> bool:
    """Ask a yes-or-no question with a default answer."""
    suffix = "[Y/n]" if default == "yes" else "[y/N]"
    while True:
        answer = input(f"{question} {suffix} ").strip().lower()
        if not answer:
            return default == "yes"
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please enter yes or no.")


def prompt_text_edit(field_name: str, current_value: str, allow_empty: bool = False) -> str:
    """Ask whether a text field should be edited and return the final value."""
    print(f"{field_name}: {current_value}")
    if not prompt_yes_no(f"Do you want to keep this {field_name.lower()}?", default="yes"):
        while True:
            new_value = input(f"Enter a new value for {field_name}: ").strip()
            if new_value or allow_empty:
                return new_value
            print(f"{field_name} cannot be empty.")
    return current_value


def print_topic(topic_data: dict) -> None:
    """Print a readable topic proposal summary."""
    print("\nGenerated topic proposal:")
    print(json.dumps(topic_data, ensure_ascii=False, indent=2))


def build_default_seo_data(topic_data: dict) -> dict:
    """Build default SEO metadata from the approved topic."""
    return {
        "seo_title": str(topic_data.get("seo_title_candidate") or topic_data.get("title_candidate") or "").strip(),
        "seo_description": str(topic_data.get("seo_description_candidate") or topic_data.get("seo_angle") or "").strip(),
        "short_description": str(topic_data.get("short_description_candidate") or "").strip(),
        "primary_keyword": str(topic_data.get("primary_keyword") or "").strip(),
        "secondary_keywords": list(topic_data.get("secondary_keywords") or []),
    }


def review_topic(state: WorkflowState) -> None:
    """Generate and approve a topic proposal interactively."""
    while state.approved_topic is None:
        topic_data = generate_new_topic(json.loads(Path(state.snapshot_path).read_text(encoding="utf-8")).get("articles", []))
        if topic_data is None:
            raise RuntimeError("Topic generation failed.")
        state.topic_attempts.append({"generated_at": utc_now(), "topic_data": topic_data})
        save_topic_locally(topic_data, source_articles_count=state.existing_articles_count, output_file=LATEST_TOPIC_FILE)
        save_state(state)
        print_topic(topic_data)
        choice = prompt_choice(
            "What do you want to do with this topic proposal?",
            {"a": "Approve it", "e": "Edit title/slug/short description manually", "r": "Regenerate a new topic"},
        )
        if choice == "r":
            continue
        if choice == "e":
            topic_data["title_candidate"] = prompt_text_edit("Title", str(topic_data.get("title_candidate", "")))
            topic_data["slug_candidate"] = prompt_text_edit("Slug", str(topic_data.get("slug_candidate", "")))
            topic_data["short_description_candidate"] = prompt_text_edit(
                "Short description",
                str(topic_data.get("short_description_candidate", "")),
            )
        state.approved_topic = topic_data
        state.status = "topic_approved"
        save_topic_locally(topic_data, source_articles_count=state.existing_articles_count, output_file=LATEST_TOPIC_FILE)
        reset_dependent_state(state)
        save_state(state)
        print("The topic has been approved.\n")


def review_seo(state: WorkflowState) -> None:
    """Review and approve SEO metadata interactively."""
    if state.approved_topic is None:
        raise RuntimeError("Topic approval is required before SEO review.")
    seo_data = dict(state.seo_data or build_default_seo_data(state.approved_topic))
    while True:
        print("\nSEO proposal:")
        print(json.dumps(seo_data, ensure_ascii=False, indent=2))
        choice = prompt_choice(
            "What do you want to do with the SEO proposal?",
            {"a": "Approve it", "e": "Edit SEO fields manually", "r": "Reset to model defaults from the topic"},
        )
        if choice == "r":
            seo_data = build_default_seo_data(state.approved_topic)
            continue
        if choice == "e":
            seo_data["seo_title"] = prompt_text_edit("SEO title", str(seo_data.get("seo_title", "")))
            seo_data["seo_description"] = prompt_text_edit("SEO description", str(seo_data.get("seo_description", "")))
            seo_data["short_description"] = prompt_text_edit("Short description", str(seo_data.get("short_description", "")))
            seo_data["primary_keyword"] = prompt_text_edit("Primary keyword", str(seo_data.get("primary_keyword", "")))
            print(f"Secondary keywords: {', '.join(seo_data.get('secondary_keywords', []))}")
            if not prompt_yes_no("Do you want to keep the current secondary keywords?", default="yes"):
                raw_keywords = input("Enter comma-separated secondary keywords: ").strip()
                seo_data["secondary_keywords"] = [item.strip() for item in raw_keywords.split(",") if item.strip()]
        state.seo_data = seo_data
        state.status = "seo_approved"
        state.article = None
        state.image = None
        state.publish = None
        save_state(state)
        print("The SEO data has been approved.\n")
        return


def generate_or_reuse_article(state: WorkflowState) -> None:
    """Generate the article body once the topic and SEO metadata are approved."""
    if state.article and state.article.get("status") == "approved":
        print("The article body is already approved. Reusing the existing draft.")
        return
    if state.approved_topic is None or state.seo_data is None:
        raise RuntimeError("Topic and SEO approval are required before article generation.")
    article_body = generate_article_body(state.approved_topic)
    if article_body is None:
        raise RuntimeError("Article generation failed.")
    validation_errors = validate_article_body(article_body)
    article_package = save_article_package(state.approved_topic, state.seo_data, article_body)
    if article_package is None:
        raise RuntimeError("Failed to save the generated article package.")
    state.article = {
        "status": "approved",
        "generated_at": utc_now(),
        "body_path": article_package["article_mdx_path"],
        "article_dir": article_package["article_dir"],
        "meta_path": article_package["article_meta_path"],
        "record_path": article_package["article_record_path"],
        "validation_errors": validation_errors,
    }
    state.status = "article_generated"
    state.image = None
    state.publish = None
    save_state(state)
    print("Generated the article body.")
    if validation_errors:
        print("Article validation warnings:")
        for error in validation_errors:
            print(f"- {error}")


def sync_image_metadata(article_dir: Path, approved_images: dict, selected_upload_format: str | None = None) -> None:
    """Write approved local image data into article metadata files."""
    meta_path = article_dir / "article_meta.json"
    record_path = article_dir / "article_record.json"
    img_url_placeholder = approved_images.get("webp") or approved_images.get("png") or ""
    for path in [meta_path, record_path]:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["img_url"] = img_url_placeholder
        payload["local_image_paths"] = approved_images
        if selected_upload_format:
            payload["selected_upload_format"] = selected_upload_format
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def persist_approved_cover_variants(attempt_cover: dict, image_dir: Path) -> dict:
    """Copy the approved attempt cover variants into stable canonical filenames."""
    approved_webp = image_dir / "final_cover.webp"
    approved_png = image_dir / "final_cover.png"
    source_webp = Path(attempt_cover["output_webp"])
    source_png = Path(attempt_cover["output_png"])
    shutil.copyfile(source_webp, approved_webp)
    shutil.copyfile(source_png, approved_png)
    return {
        "webp": str(approved_webp).replace("\\", "/"),
        "png": str(approved_png).replace("\\", "/"),
    }


def prompt_image_upload_format(current_value: str | None = None) -> str:
    """Ask which final image format should be uploaded to Spaces."""
    if current_value in {"png", "webp"}:
        print(f"Current image upload format: {current_value}")
    choice = prompt_choice(
        "Which image format should be uploaded to DigitalOcean Spaces?",
        {"webp": "Upload WebP", "png": "Upload PNG"},
    )
    return choice


def review_image(state: WorkflowState) -> None:
    """Generate and approve a cover image interactively."""
    if state.article is None:
        raise RuntimeError("The article must exist before image generation.")
    article_dir = Path(state.article["article_dir"])
    image_dir = article_dir / "images"
    if state.image and state.image.get("status") == "approved":
        approved_files = state.image.get("approved_local_files", {})
        if approved_files.get("png") and approved_files.get("webp"):
            print("An approved image already exists for this article.")
            print(f"- PNG: {approved_files['png']}")
            print(f"- WebP: {approved_files['webp']}")
            if prompt_yes_no("Do you want to keep the approved image and continue?", default="yes"):
                return
    approved = False
    while not approved:
        attempt_dir = image_dir / f"attempt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        generation_result = generate_cover_background({"topic_data": state.approved_topic}, attempt_dir / "raw")
        if generation_result is None:
            raise RuntimeError("Image generation failed.")
        raw_images = generation_result.get("images", [])
        if not raw_images:
            raise RuntimeError("Image generation returned no images.")
        final_cover = create_final_cover(
            title=str(state.approved_topic.get("title_candidate", "")).strip(),
            source_image_path=Path(raw_images[0]),
            output_dir=attempt_dir,
        )
        if final_cover is None:
            raise RuntimeError("Final cover creation failed.")
        print("\nImage review:")
        print(f"PNG preview file: {final_cover['output_png']}")
        print(f"WebP preview file: {final_cover['output_webp']}")
        print("Open the generated files locally to review them. Most IDE terminals cannot render images inline.")
        choice = prompt_choice(
            "What do you want to do with this image attempt?",
            {"a": "Approve it", "r": "Regenerate another image"},
        )
        if choice == "r":
            continue
        approved_images = persist_approved_cover_variants(final_cover, image_dir)
        selected_upload_format = prompt_image_upload_format(state.image.get("selected_upload_format") if state.image else None)
        approved = True
        state.image = {
            "status": "approved",
            "generated_at": utc_now(),
            "raw_generation": generation_result,
            "attempt_cover": final_cover,
            "approved_local_files": approved_images,
            "selected_upload_format": selected_upload_format,
        }
        sync_image_metadata(article_dir, approved_images, selected_upload_format)
        state.status = "image_approved"
        state.publish = None
        save_state(state)
        print("The image has been approved. The approved cover files were updated.\n")


def ask_publish_decision(state: WorkflowState) -> None:
    """Ask whether the fully prepared article should be published."""
    if state.article is None or state.image is None:
        raise RuntimeError("Article and image approval are required before publication.")
    if state.publish and state.publish.get("status") in {"published", "skipped"}:
        print(f"Publish decision already recorded: {state.publish['status']}.")
        return
    article_dir = Path(state.article["article_dir"])
    if prompt_yes_no("Do you want to change the image upload format before publishing?", default="no"):
        state.image["selected_upload_format"] = prompt_image_upload_format(state.image.get("selected_upload_format"))
        sync_image_metadata(article_dir, state.image.get("approved_local_files", {}), state.image["selected_upload_format"])
        save_state(state)
    print("\nFinal summary before publication:")
    print(f"- Published articles already in MongoDB: {state.existing_articles_count}")
    print(f"- Approved topic: {state.approved_topic.get('title_candidate')}")
    print(f"- Approved slug: {state.approved_topic.get('slug_candidate')}")
    print(f"- Article directory: {article_dir}")
    print(f"- Local PNG cover: {state.image['approved_local_files']['png']}")
    print(f"- Local WebP cover: {state.image['approved_local_files']['webp']}")
    print(f"- Upload format: {state.image['selected_upload_format']}")
    if prompt_yes_no("Do you want to publish this article now?", default="no"):
        publish_result = publish_article(article_dir, image_format=state.image["selected_upload_format"])
        if publish_result is None:
            raise RuntimeError("Publication failed.")
        state.publish = {"status": publish_result.get("status", "published"), "result": publish_result, "decided_at": utc_now()}
        state.status = "published" if publish_result.get("status") == "published" else publish_result.get("status")
    else:
        state.publish = {"status": "skipped", "decided_at": utc_now()}
        state.status = "ready_to_publish"
    save_state(state)


def archive_published_workflow(state: WorkflowState) -> None:
    """Archive the current workflow state once the article is published."""
    if state.status != "published" or state.approved_topic is None:
        return
    slug = str(state.approved_topic.get("slug_candidate", "")).strip() or "published-article"
    archive_path = WORKFLOW_DIR / f"workflow_{slug}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copyfile(WORKFLOW_STATE_FILE, archive_path)
    print(f"Archived the published workflow state to {archive_path}.")


def run_workflow() -> None:
    """Run the end-to-end interactive article workflow."""
    print("Starting the automatic articles workflow.")
    state = load_state()
    if state.status == "published":
        print("The previous workflow is already published. Starting a fresh workflow run.")
        state = create_empty_state()
        save_state(state)
    snapshot = refresh_existing_articles_snapshot()
    state.existing_articles_count = snapshot["count"]
    state.snapshot_path = snapshot["snapshot_path"]
    save_state(state)
    print(f"Found {state.existing_articles_count} published en-US articles in MongoDB.")
    if state.approved_topic:
        print(f"Resuming workflow from approved topic: {state.approved_topic.get('title_candidate')}")
    review_topic(state)
    review_seo(state)
    generate_or_reuse_article(state)
    review_image(state)
    ask_publish_decision(state)
    archive_published_workflow(state)
    print(f"Workflow finished with status: {state.status}")


if __name__ == "__main__":
    run_workflow()
