import json
import os
from datetime import datetime, timezone

from connections.novita_connection import get_novita_client
from config import novita


INPUT_FILE = "generated_articles/source_data/existing_articles.json"
OUTPUT_DIR = "generated_articles/topic_generation"
OUTPUT_FILE = "latest_topic.json"


def ensure_output_dir():
    """Создает папку для локального сохранения, если ее нет."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_existing_articles():
    """
    Загружает локальный snapshot существующих статей из JSON.
    """
    if not os.path.exists(INPUT_FILE):
        print(f"Файл не найден: {INPUT_FILE}")
        return []

    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        articles = data.get("articles", [])
        return articles

    except Exception as e:
        print(f"Ошибка при загрузке existing_articles.json: {e}")
        return []


def build_existing_articles_context(existing_articles, limit=200):
    """
    Формирует компактный контекст по существующим статьям.
    Берем title, slug, seo_title и seo_description.
    """
    context_blocks = []

    for article in existing_articles[:limit]:
        title = article.get("title", "").strip()
        slug = article.get("url_slug", "").strip()
        seo_title = article.get("seo_title", "").strip()
        seo_description = article.get("seo_description", "").strip()
        short_description = article.get("short_description", "").strip()

        block = (
            f"- Title: {title}\n"
            f"  Slug: {slug}\n"
            f"  SEO Title: {seo_title}\n"
            f"  SEO Description: {seo_description}\n"
            f"  Short Description: {short_description}"
        )
        context_blocks.append(block)

    return "\n".join(context_blocks)


def build_topic_generation_prompt(existing_articles):
    """
    Формирует prompt для генерации новой темы статьи.
    """
    existing_context = build_existing_articles_context(existing_articles)

    prompt = f"""
You are an expert startup content strategist for a blog focused on:
startup fundraising, investor discovery, VC outreach, angel investors, pitch decks, startup valuation, and how founders find investors.

Your task:
Propose ONE new article topic in English for this blog.

Requirements:
1. The topic must be highly relevant to startup founders looking for investors.
2. The topic must NOT duplicate or be too similar to existing articles.
3. The topic should be practical, useful, and SEO-friendly.
4. The topic should be specific enough to become a strong long-form article.
5. The topic should fit naturally into this blog's existing editorial style.
6. Avoid generic topics that have likely already been covered many times.
7. Prefer topics with strong search intent and practical founder value.
8. Return valid JSON only.
9. Language must be English.
10. The proposed title should be original, clear, and suitable for an SEO article.
11. The proposed slug must be unique compared to the existing slugs.
12. short_description_candidate must be 1 to 2 short sentences and under 150 characters.

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
  "seo_angle": "string"
}}
"""
    return prompt.strip()


def generate_new_topic():
    """
    Генерирует новую тему статьи через Novita.
    Возвращает dict или None.
    """
    existing_articles = load_existing_articles()

    if not existing_articles:
        print("Список существующих статей пуст или недоступен.")
        return None

    prompt = build_topic_generation_prompt(existing_articles)

    try:
        client = get_novita_client()

        response = client.chat.completions.create(
            model=novita["model"],
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise content strategist and SEO planner. "
                        "Return valid JSON only. Do not include markdown fences."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=900,
            response_format={"type": "json_object"}
        )

        raw_content = response.choices[0].message.content
        topic_data = json.loads(raw_content)

        return topic_data

    except Exception as e:
        print(f"Ошибка при генерации новой темы: {e}")
        return None


def save_topic_locally(topic_data, source_articles_count):
    """
    Сохраняет результат генерации темы локально в JSON.
    """
    ensure_output_dir()

    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "generated_at": now_iso,
        "provider": "novita",
        "model": novita["model"],
        "source_snapshot_file": INPUT_FILE,
        "source_articles_count": source_articles_count,
        "topic_data": topic_data
    }

    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print("Новая тема успешно сгенерирована и сохранена локально.")
        print(f"Файл: {output_path}")
        print("Сгенерированная тема:")
        print(json.dumps(topic_data, ensure_ascii=False, indent=2))

        return output_path

    except Exception as e:
        print(f"Ошибка при сохранении темы локально: {e}")
        return None


def main():
    existing_articles = load_existing_articles()

    if not existing_articles:
        print("Не удалось загрузить existing_articles.json.")
        return

    print(f"Загружено существующих статей из snapshot: {len(existing_articles)}")

    topic_data = generate_new_topic()

    if topic_data is None:
        print("Не удалось сгенерировать новую тему.")
        return

    save_topic_locally(topic_data, source_articles_count=len(existing_articles))


if __name__ == "__main__":
    main()