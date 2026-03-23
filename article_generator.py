from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from connections.novita_connection import get_novita_client
from config import novita


BASE_OUTPUT_DIR = Path("generated_articles/en")


def normalize_slug(slug: str) -> str:
    """Normalize a slug value to a safe lowercase URL slug."""
    slug = (slug or "").strip().lower()
    slug = re.sub(r"[^a-z0-9 -]", "", slug)
    slug = slug.replace(" ", "-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def normalize_short_description(text: str, max_chars: int = 150) -> str:
    """Normalize a short description to at most two sentences and max_chars."""
    if not text:
        return ""
    text = " ".join(str(text).strip().split())
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    short_text = " ".join(sentences[:2]).strip()
    if short_text and short_text[-1] not in ".!?":
        short_text += "."
    if len(short_text) > max_chars:
        truncated = short_text[:max_chars].rstrip()
        last_space = truncated.rfind(" ")
        if last_space > 80:
            truncated = truncated[:last_space]
        short_text = truncated.rstrip(" ,;:-") + "."
    return short_text


def clean_generated_text(text: str) -> str:
    """Clean common model artifacts from generated Markdown."""
    if not text:
        return ""
    replacements = {
        "â€™": "'",
        "â€œ": '"',
        "â€\x9d": '"',
        "â€“": "–",
        "â€”": "—",
        "â€¦": "...",
        "Â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = text.strip()
    for prefix in ("```mdx", "```markdown", "```md", "```"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    if text.endswith("```"):
        text = text[:-3].strip()
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\[L\d+(?:-L?\d+)?\]", "", text)
    text = re.sub(r"【[^】]+】", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def build_article_body_prompt(topic_data: dict) -> str:
    """Build the article-body prompt from approved topic metadata."""
    secondary_keywords_text = ", ".join(topic_data.get("secondary_keywords", []))
    return f"""
You are a senior B2B startup content writer and SEO editor.

Write only the BODY of a publication-ready MDX/Markdown article in English for a blog focused on startup fundraising, investor discovery, VC outreach, angel investors, and founder education.

Topic data:
- Title: {topic_data.get('title_candidate', '').strip()}
- Slug: {topic_data.get('slug_candidate', '').strip()}
- Reasoning summary: {topic_data.get('reasoning_summary', '').strip()}
- Search intent: {topic_data.get('search_intent', '').strip()}
- Target audience: {topic_data.get('target_audience', '').strip()}
- Primary keyword: {topic_data.get('primary_keyword', '').strip()}
- Secondary keywords: {secondary_keywords_text}
- SEO angle: {topic_data.get('seo_angle', '').strip()}

Important:
1. Do not generate YAML frontmatter.
2. Do not generate the title at the top.
3. Do not generate the slug.
4. Do not generate meta descriptions.
5. Return only the article body.
6. Output must be valid clean Markdown/MDX.
7. Do not wrap the response in triple backticks.

Content requirements:
1. Start with a strong introduction of 2 to 4 paragraphs.
2. Include 5 to 7 H2 sections using "## ".
3. Use short readable paragraphs.
4. Use bullet lists where they help readability.
5. Include practical advice for startup founders.
6. Use the primary keyword naturally in the introduction, at least one H2 heading, and the body.
7. Use the secondary keywords naturally without stuffing.
8. Add a section titled "## FAQ".
9. Under FAQ include exactly 3 H3 questions using "### ".
10. Add a final section called "## Further reading".
11. Under Further reading include 3 to 5 real markdown links to external sources.
12. Do not output raw citation markers like [1], [2], [L10-L20], or placeholders.
13. Do not invent fake statistics.
14. Do not use tables.
15. Avoid HTML unless absolutely necessary.
16. Keep formatting clean and publication-ready.
17. Separate paragraphs with blank lines.

Return only the article body.
""".strip()


def generate_article_body(topic_data: dict) -> str | None:
    """Generate the article body through Novita."""
    prompt = build_article_body_prompt(topic_data)
    try:
        client = get_novita_client()
        response = client.chat.completions.create(
            model=novita["model"],
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise long-form startup content writer and SEO editor. Return only clean article body in Markdown/MDX without YAML frontmatter or markdown fences.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=5000,
        )
        raw_content = response.choices[0].message.content
        if not raw_content or not str(raw_content).strip():
            print("The model returned an empty article body.")
            return None
        return clean_generated_text(raw_content)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to generate the article body: {exc}")
        return None


def validate_article_body(article_body: str) -> list[str]:
    """Run a basic structural validation against the generated body."""
    errors: list[str] = []
    if not article_body or len(article_body.strip()) < 800:
        errors.append("The article body is too short or empty.")
    h2_count = len(re.findall(r"^## ", article_body, flags=re.MULTILINE))
    if h2_count < 5:
        errors.append(f"Too few H2 sections: {h2_count}.")
    if "## FAQ" not in article_body:
        errors.append("The FAQ section is missing.")
    faq_h3_count = len(re.findall(r"^### ", article_body, flags=re.MULTILINE))
    if faq_h3_count < 3:
        errors.append(f"Too few FAQ questions: {faq_h3_count}.")
    if "## Further reading" not in article_body:
        errors.append("The Further reading section is missing.")
    link_count = len(re.findall(r"\[.*?\]\(https?://.*?\)", article_body))
    if link_count < 3:
        errors.append(f"Too few external links: {link_count}.")
    return errors


def yaml_escape(value: str) -> str:
    """Escape a string for YAML frontmatter."""
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def build_frontmatter(topic_data: dict, seo_data: dict) -> str:
    """Build YAML frontmatter from approved topic and SEO data."""
    title = str(topic_data.get("title_candidate") or "").strip()
    slug = normalize_slug(topic_data.get("slug_candidate") or "")
    primary_keyword = str(seo_data.get("primary_keyword") or topic_data.get("primary_keyword") or "").strip()
    secondary_keywords = seo_data.get("secondary_keywords") or topic_data.get("secondary_keywords") or []
    publish_date = datetime.now(timezone.utc).isoformat()
    seo_title = str(seo_data.get("seo_title") or title).strip()
    seo_description = str(seo_data.get("seo_description") or topic_data.get("seo_description_candidate") or topic_data.get("seo_angle") or "").strip()
    short_description = normalize_short_description(
        str(seo_data.get("short_description") or topic_data.get("short_description_candidate") or topic_data.get("reasoning_summary") or "")
    )
    lines = [
        "---",
        f'title: "{yaml_escape(title)}"',
        f'slug: "{yaml_escape(slug)}"',
        f'seo_title: "{yaml_escape(seo_title)}"',
        f'seo_description: "{yaml_escape(seo_description)}"',
        f'short_description: "{yaml_escape(short_description)}"',
        'lang: "en-US"',
        'status: "draft"',
        f'publish_date: "{yaml_escape(publish_date)}"',
        f'primary_keyword: "{yaml_escape(primary_keyword)}"',
        "secondary_keywords:",
    ]
    for keyword in secondary_keywords:
        lines.append(f'  - "{yaml_escape(str(keyword).strip())}"')
    lines.append("---")
    return "\n".join(lines)


def build_article_meta(topic_data: dict, seo_data: dict) -> dict:
    """Build the article metadata JSON payload."""
    title = str(topic_data.get("title_candidate") or "").strip()
    slug = normalize_slug(topic_data.get("slug_candidate") or "")
    return {
        "title": title,
        "url_slug": slug,
        "short_description": normalize_short_description(
            str(seo_data.get("short_description") or topic_data.get("short_description_candidate") or topic_data.get("reasoning_summary") or "")
        ),
        "seo_title": str(seo_data.get("seo_title") or title).strip(),
        "seo_description": str(seo_data.get("seo_description") or topic_data.get("seo_description_candidate") or topic_data.get("seo_angle") or "").strip(),
        "lang": "en-US",
        "status": "draft",
        "publish_date": datetime.now(timezone.utc).isoformat(),
        "primary_keyword": str(seo_data.get("primary_keyword") or topic_data.get("primary_keyword") or "").strip(),
        "secondary_keywords": seo_data.get("secondary_keywords") or topic_data.get("secondary_keywords", []),
        "img_url": "",
        "content_url": "",
    }


def build_article_record(meta: dict, article_dir: Path) -> dict:
    """Build the local tracking record for an article draft."""
    return {
        "title": meta.get("title", ""),
        "url_slug": meta.get("url_slug", ""),
        "content_url": "",
        "publish_date": meta.get("publish_date", ""),
        "alternative_urls": [""],
        "short_description": meta.get("short_description", ""),
        "seo_title": meta.get("seo_title", ""),
        "seo_description": meta.get("seo_description", ""),
        "img_url": "",
        "status": meta.get("status", "draft"),
        "lang": meta.get("lang", "en-US"),
        "internal_meta": {
            "provider": "novita",
            "model": novita["model"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "local_article_dir": str(article_dir).replace("\\", "/"),
        },
    }


def save_article_package(topic_data: dict, seo_data: dict, article_body: str) -> dict | None:
    """Persist the generated article package to disk."""
    meta = build_article_meta(topic_data, seo_data)
    slug = meta["url_slug"]
    if not slug:
        print("The article slug is missing or invalid.")
        return None
    article_dir = BASE_OUTPUT_DIR / slug
    article_dir.mkdir(parents=True, exist_ok=True)
    final_mdx = f"{build_frontmatter(topic_data, seo_data)}\n\n{article_body.strip()}\n"
    article_record = build_article_record(meta, article_dir)
    try:
        (article_dir / "article.mdx").write_text(final_mdx, encoding="utf-8")
        (article_dir / "article_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (article_dir / "article_record.json").write_text(json.dumps(article_record, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Saved the article package locally.")
        print(f"Article directory: {article_dir}")
        return {
            "article_dir": str(article_dir).replace("\\", "/"),
            "article_mdx_path": str((article_dir / 'article.mdx')).replace("\\", "/"),
            "article_meta_path": str((article_dir / 'article_meta.json')).replace("\\", "/"),
            "article_record_path": str((article_dir / 'article_record.json')).replace("\\", "/"),
            "meta": meta,
        }
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to save the article package: {exc}")
        return None
