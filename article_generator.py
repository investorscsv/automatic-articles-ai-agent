import json
import os
import re
from datetime import datetime, timezone

from connections.novita_connection import get_novita_client
from config import novita


TOPIC_FILE = "generated_articles/topic_generation/latest_topic.json"
BASE_OUTPUT_DIR = "generated_articles/en"


def load_json_file(file_path):
    """Загружает JSON-файл и возвращает dict."""
    if not os.path.exists(file_path):
        print(f"Файл не найден: {file_path}")
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка при чтении JSON-файла {file_path}: {e}")
        return None


def ensure_article_output_dir(slug):
    """Создает папку статьи по slug."""
    article_dir = os.path.join(BASE_OUTPUT_DIR, slug)
    os.makedirs(article_dir, exist_ok=True)
    return article_dir


def normalize_slug(slug: str) -> str:
    """Нормализует slug на случай странных символов."""
    slug = (slug or "").strip().lower()
    slug = re.sub(r"[^a-z0-9 -]", "", slug)
    slug = slug.replace(" ", "-")
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    return slug

def normalize_short_description(text: str, max_chars: int = 150) -> str:
    """
    Приводит short_description к короткому формату:
    - максимум 2 предложения
    - максимум max_chars символов
    - без лишних пробелов
    """
    if not text:
        return ""

    text = " ".join(str(text).strip().split())

    if not text:
        return ""

    import re

    # Делим на предложения по ., !, ?
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # Берем максимум 2 предложения
    short_text = " ".join(sentences[:2]).strip()

    # Если после разбиения текст без финальной точки и был одним предложением
    if short_text and short_text[-1] not in ".!?":
        short_text += "."

    # Ограничиваем длину
    if len(short_text) > max_chars:
        truncated = short_text[:max_chars].rstrip()

        # Пытаемся обрезать по последнему пробелу, чтобы не ломать слово
        last_space = truncated.rfind(" ")
        if last_space > 80:
            truncated = truncated[:last_space]

        short_text = truncated.rstrip(" ,;:-") + "."

    return short_text

def clean_generated_text(text: str) -> str:
    """
    Чистит типичный мусор модели:
    - [1], [12], [L34-L40]
    - markdown fences
    - битую типографику / mojibake
    - лишние пробелы
    """
    if not text:
        return ""

    replacements = {
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
        "â€“": "–",
        "â€”": "—",
        "â€¦": "...",
        "Â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    text = text.strip()

    if text.startswith("```mdx"):
        text = text[len("```mdx"):].strip()
    elif text.startswith("```markdown"):
        text = text[len("```markdown"):].strip()
    elif text.startswith("```md"):
        text = text[len("```md"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\[L\d+(?:-L?\d+)?\]", "", text)
    text = re.sub(r"【[^】]+】", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def build_article_body_prompt(topic_data):
    """
    Формирует prompt только для body статьи.
    Все мета-данные берем из latest_topic.json и не просим модель генерировать их заново.
    """
    title_candidate = topic_data.get("title_candidate", "").strip()
    slug_candidate = topic_data.get("slug_candidate", "").strip()
    reasoning_summary = topic_data.get("reasoning_summary", "").strip()
    search_intent = topic_data.get("search_intent", "").strip()
    target_audience = topic_data.get("target_audience", "").strip()
    primary_keyword = topic_data.get("primary_keyword", "").strip()
    secondary_keywords = topic_data.get("secondary_keywords", [])
    seo_angle = topic_data.get("seo_angle", "").strip()

    secondary_keywords_text = ", ".join(secondary_keywords)

    prompt = f"""
You are a senior B2B startup content writer and SEO editor.

Write only the BODY of a publication-ready MDX/Markdown article in English for a blog focused on startup fundraising, investor discovery, VC outreach, angel investors, and founder education.

Topic data:
- Title: {title_candidate}
- Slug: {slug_candidate}
- Reasoning summary: {reasoning_summary}
- Search intent: {search_intent}
- Target audience: {target_audience}
- Primary keyword: {primary_keyword}
- Secondary keywords: {secondary_keywords_text}
- SEO angle: {seo_angle}

Important:
1. Do NOT generate YAML frontmatter.
2. Do NOT generate title at the top.
3. Do NOT generate slug.
4. Do NOT generate meta description.
5. Return only the article body.
6. Output must be valid, clean Markdown/MDX.
7. Do not wrap the response in triple backticks.

Content requirements:
1. Start with a strong introduction of 2 to 4 paragraphs.
2. Include 5 to 7 H2 sections using "## ".
3. Use short readable paragraphs.
4. Use bullet lists where they help readability.
5. Include practical advice for startup founders.
6. Use the primary keyword naturally in the introduction, at least one H2 heading, and body.
7. Use the secondary keywords naturally without stuffing.
8. Add a section "## FAQ".
9. Under FAQ include exactly 3 H3 questions using "### ".
10. Add a final section called "## Further reading".
11. Under "Further reading", include 3 to 5 real markdown links to external sources.
12. Do not output raw citation markers like [1], [2], [L10-L20], or placeholders.
13. Do not invent fake statistics.
14. Do not use tables.
15. Avoid HTML unless absolutely necessary.
16. Keep formatting clean and publication-ready.
17. Separate paragraphs with blank lines.

Return only the article body.
"""
    return prompt.strip()


def generate_article_body(topic_data):
    """
    Генерирует только body статьи через Novita.
    """
    prompt = build_article_body_prompt(topic_data)

    try:
        client = get_novita_client()

        response = client.chat.completions.create(
            model=novita["model"],
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise long-form startup content writer and SEO editor. "
                        "Return only clean article body in Markdown/MDX. "
                        "Do not include YAML frontmatter. "
                        "Do not include markdown fences."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.5,
            max_tokens=5000
        )

        raw_content = response.choices[0].message.content

        print("RAW CONTENT PREVIEW:")
        print(repr(raw_content[:700] if raw_content else raw_content))

        if not raw_content or not str(raw_content).strip():
            print("Модель вернула пустой content.")
            print("FULL RESPONSE:")
            print(response)
            return None

        article_body = clean_generated_text(raw_content)
        return article_body

    except Exception as e:
        print(f"Ошибка при генерации body статьи: {e}")
        if "response" in locals():
            print("FULL RESPONSE:")
            print(response)
        return None


def validate_article_body(article_body: str):
    """
    Базовая проверка структуры body.
    """
    errors = []

    if not article_body or len(article_body.strip()) < 800:
        errors.append("Текст статьи слишком короткий или пустой.")

    h2_count = len(re.findall(r"^## ", article_body, flags=re.MULTILINE))
    if h2_count < 5:
        errors.append(f"Слишком мало H2 секций: {h2_count}")

    if "## FAQ" not in article_body:
        errors.append("Отсутствует секция FAQ.")

    faq_h3_count = len(re.findall(r"^### ", article_body, flags=re.MULTILINE))
    if faq_h3_count < 3:
        errors.append(f"Слишком мало FAQ вопросов: {faq_h3_count}")

    if "## Further reading" not in article_body:
        errors.append("Отсутствует секция Further reading.")

    link_count = len(re.findall(r"\[.*?\]\(https?://.*?\)", article_body))
    if link_count < 3:
        errors.append(f"Слишком мало внешних ссылок: {link_count}")

    return errors


def yaml_escape(value: str) -> str:
    """
    Безопасно экранирует строку для YAML frontmatter.
    """
    value = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    return value


def build_frontmatter(topic_data):
    """
    Собирает frontmatter ИСКЛЮЧИТЕЛЬНО из latest_topic.json.
    Ничего не берем из ответа модели.
    """
    title = (topic_data.get("title_candidate") or "").strip()
    slug = normalize_slug(topic_data.get("slug_candidate") or "")
    primary_keyword = (topic_data.get("primary_keyword") or "").strip()
    secondary_keywords = topic_data.get("secondary_keywords") or []
    publish_date = datetime.now(timezone.utc).isoformat()

    seo_title = title
    seo_description = (topic_data.get("seo_angle") or "").strip()
    short_description = normalize_short_description(
        topic_data.get("short_description_candidate")
        or topic_data.get("reasoning_summary")
        or ""
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
        "secondary_keywords:"
    ]

    for keyword in secondary_keywords:
        lines.append(f'  - "{yaml_escape(str(keyword).strip())}"')

    lines.append("---")

    return "\n".join(lines)


def build_final_mdx(topic_data, article_body: str):
    """
    Собирает итоговый article.mdx:
    frontmatter из latest_topic.json + body от модели.
    """
    frontmatter = build_frontmatter(topic_data)
    article_body = article_body.strip()
    return f"{frontmatter}\n\n{article_body}\n"


def build_article_meta(topic_data):
    """
    Мета-данные статьи на основе latest_topic.json.
    """
    title = (topic_data.get("title_candidate") or "").strip()
    slug = normalize_slug(topic_data.get("slug_candidate") or "")
    primary_keyword = (topic_data.get("primary_keyword") or "").strip()

    return {
        "title": title,
        "url_slug": slug,
        "short_description": normalize_short_description(
        topic_data.get("short_description_candidate")
        or topic_data.get("reasoning_summary")
        or ""
        ),
        "seo_title": title,
        "seo_description": (topic_data.get("seo_angle") or "").strip(),
        "lang": "en-US",
        "status": "draft",
        "publish_date": datetime.now(timezone.utc).isoformat(),
        "primary_keyword": primary_keyword,
        "secondary_keywords": topic_data.get("secondary_keywords", [])
    }


def build_article_record(meta):
    """
    Строит краткий внутренний record-файл для локального учета.
    """
    slug = meta["url_slug"]

    return {
        "title": meta.get("title", ""),
        "url_slug": slug,
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
            "local_article_dir": f"generated_articles/en/{slug}"
        }
    }


def save_article_files(topic_data, article_body):
    """
    Сохраняет article.mdx, article_meta.json и article_record.json.
    """
    meta = build_article_meta(topic_data)
    slug = meta["url_slug"]

    if not slug:
        print("У статьи отсутствует корректный slug.")
        return None

    article_dir = ensure_article_output_dir(slug)

    article_mdx_path = os.path.join(article_dir, "article.mdx")
    article_meta_path = os.path.join(article_dir, "article_meta.json")
    article_record_path = os.path.join(article_dir, "article_record.json")

    final_mdx = build_final_mdx(topic_data, article_body)
    article_record = build_article_record(meta)

    try:
        with open(article_mdx_path, "w", encoding="utf-8") as f:
            f.write(final_mdx)

        with open(article_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        with open(article_record_path, "w", encoding="utf-8") as f:
            json.dump(article_record, f, ensure_ascii=False, indent=2)

        print("Статья успешно сгенерирована и сохранена локально.")
        print(f"Папка статьи: {article_dir}")
        print(f"article.mdx: {article_mdx_path}")
        print(f"article_meta.json: {article_meta_path}")
        print(f"article_record.json: {article_record_path}")

        return article_dir

    except Exception as e:
        print(f"Ошибка при сохранении файлов статьи: {e}")
        return None


def main():
    topic_payload = load_json_file(TOPIC_FILE)

    if topic_payload is None:
        print("Не удалось загрузить latest_topic.json.")
        return

    topic_data = topic_payload.get("topic_data")

    if not topic_data:
        print("В latest_topic.json отсутствует topic_data.")
        return

    required_fields = [
        "title_candidate",
        "slug_candidate",
        "reasoning_summary",
        "search_intent",
        "target_audience",
        "primary_keyword",
        "secondary_keywords",
        "seo_angle",
    ]

    missing_fields = [field for field in required_fields if field not in topic_data or topic_data.get(field) in [None, ""]]
    if missing_fields:
        print("В topic_data отсутствуют обязательные поля:")
        for field in missing_fields:
            print(f"- {field}")
        return

    article_body = generate_article_body(topic_data)

    if article_body is None:
        print("Не удалось сгенерировать body статьи.")
        return

    validation_errors = validate_article_body(article_body)
    if validation_errors:
        print("Статья сгенерирована, но есть замечания по структуре:")
        for err in validation_errors:
            print(f"- {err}")

    save_article_files(topic_data, article_body)


if __name__ == "__main__":
    main()