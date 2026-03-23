from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from connections.mongo_connection import get_blog_articles_collection


OUTPUT_DIR = Path("generated_articles/source_data")
OUTPUT_FILE = OUTPUT_DIR / "existing_articles.json"


def ensure_output_dir() -> None:
    """Create the output directory when it does not exist yet."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_existing_articles() -> list[dict]:
    """Fetch published English-language articles from MongoDB."""
    collection = get_blog_articles_collection()

    if collection is None:
        print("Failed to get the blog articles collection.")
        return []

    try:
        cursor = collection.find(
            {"lang": "en-US", "status": "published"},
            {
                "_id": 0,
                "title": 1,
                "url_slug": 1,
                "seo_title": 1,
                "seo_description": 1,
                "short_description": 1,
                "lang": 1,
                "status": 1,
                "img_url": 1,
                "content_url": 1,
            },
        )
        articles: list[dict] = []
        for doc in cursor:
            articles.append(
                {
                    "title": str(doc.get("title", "")).strip(),
                    "url_slug": str(doc.get("url_slug", "")).strip(),
                    "seo_title": str(doc.get("seo_title", "")).strip(),
                    "seo_description": str(doc.get("seo_description", "")).strip(),
                    "short_description": str(doc.get("short_description", "")).strip(),
                    "lang": str(doc.get("lang", "")).strip(),
                    "status": str(doc.get("status", "")).strip(),
                    "img_url": str(doc.get("img_url", "")).strip(),
                    "content_url": str(doc.get("content_url", "")).strip(),
                }
            )
        return articles
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to fetch articles from MongoDB: {exc}")
        return []


def save_existing_articles_snapshot(articles: list[dict]) -> Path | None:
    """Save a local snapshot of the existing articles list."""
    ensure_output_dir()
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": len(articles),
        "articles": articles,
    }
    try:
        OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Saved the existing articles snapshot.")
        print(f"Snapshot file: {OUTPUT_FILE}")
        return OUTPUT_FILE
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to save the existing articles snapshot: {exc}")
        return None


def refresh_existing_articles_snapshot() -> dict:
    """Fetch published articles and persist a fresh snapshot."""
    articles = get_existing_articles()
    snapshot_path = save_existing_articles_snapshot(articles)
    return {
        "articles": articles,
        "count": len(articles),
        "snapshot_path": str(snapshot_path) if snapshot_path else "",
    }


if __name__ == "__main__":
    result = refresh_existing_articles_snapshot()
    print(f"Found {result['count']} published en-US articles.")
