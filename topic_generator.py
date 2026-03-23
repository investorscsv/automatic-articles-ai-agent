from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from connections.novita_connection import get_novita_client
from config import novita


DEFAULT_OUTPUT_DIR = Path("generated_articles/topic_generation")
DEFAULT_OUTPUT_FILE = DEFAULT_OUTPUT_DIR / "latest_topic.json"


def ensure_output_dir(output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    """Create the topic output directory when needed."""
    output_dir.mkdir(parents=True, exist_ok=True)


def build_existing_articles_context(existing_articles: list[dict], limit: int = 200) -> str:
    """Build a compact context block from existing article metadata."""
    context_blocks: list[str] = []
    for article in existing_articles[:limit]:
        block = (
            f"- Title: {str(article.get('title', '')).strip()}\n"
            f"  Slug: {str(article.get('url_slug', '')).strip()}\n"
            f"  SEO Title: {str(article.get('seo_title', '')).strip()}\n"
            f"  SEO Description: {str(article.get('seo_description', '')).strip()}\n"
            f"  Short Description: {str(article.get('short_description', '')).strip()}"
        )
        context_blocks.append(block)
    return "\n".join(context_blocks)


def build_topic_generation_prompt(existing_articles: list[dict]) -> str:
    """Build the topic-generation prompt."""
    existing_context = build_existing_articles_context(existing_articles)
    return f"""
You are an expert startup content strategist for a blog focused on startup fundraising, investor discovery, VC outreach, angel investors, pitch decks, startup valuation, and how founders find investors.

Your task is to propose exactly one new article topic in English.

Requirements:
1. The topic must be highly relevant to startup founders looking for investors.
2. The topic must not duplicate or be too similar to existing articles.
3. The topic should be practical, useful, and SEO-friendly.
4. The topic should be specific enough to become a strong long-form article.
5. The topic should fit the existing editorial style naturally.
6. Avoid generic topics.
7. Prefer topics with strong search intent and practical founder value.
8. Return valid JSON only.
9. The language must be English.
10. The proposed title should be original, clear, and suitable for SEO.
11. The proposed slug must be unique compared with the existing slugs.
12. short_description_candidate must be 1 to 2 short sentences and under 150 characters.
13. Provide seo_title_candidate and seo_description_candidate.

Existing articles:
{existing_context}

Return JSON in exactly this format:
{{
  "title_candidate": "string",
  "slug_candidate": "string",
  "reasoning_summary": "string",
  "short_description_candidate": "string",
  "search_intent": "string",
  "target_audience": "string",
  "primary_keyword": "string",
  "secondary_keywords": ["string", "string", "string"],
  "seo_angle": "string",
  "seo_title_candidate": "string",
  "seo_description_candidate": "string"
}}
""".strip()


def generate_new_topic(existing_articles: list[dict]) -> dict | None:
    """Generate one topic proposal through Novita."""
    if not existing_articles:
        print("The existing articles list is empty or unavailable.")
        return None

    prompt = build_topic_generation_prompt(existing_articles)

    try:
        client = get_novita_client()
        response = client.chat.completions.create(
            model=novita["model"],
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise content strategist and SEO planner. Return valid JSON only without markdown fences.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content
        return json.loads(raw_content)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to generate a new topic: {exc}")
        return None


def save_topic_locally(topic_data: dict, source_articles_count: int, output_file: Path = DEFAULT_OUTPUT_FILE) -> Path | None:
    """Save the latest topic proposal as JSON."""
    ensure_output_dir(output_file.parent)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "novita",
        "model": novita["model"],
        "source_articles_count": source_articles_count,
        "topic_data": topic_data,
    }
    try:
        output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Saved the topic proposal locally.")
        print(f"Topic file: {output_file}")
        return output_file
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to save the topic proposal: {exc}")
        return None
