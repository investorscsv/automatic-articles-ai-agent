import json
import os
from datetime import datetime, timezone

from connections.mongo_connection import get_blog_articles_collection


OUTPUT_DIR = "generated_articles/source_data"
OUTPUT_FILE = "existing_articles.json"


def ensure_output_dir():
    """Создает папку для локального сохранения, если ее нет."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_existing_articles():
    """
    Возвращает список существующих статей из MongoDB.
    Берет только нужные поля для дальнейшей генерации контента.
    """
    collection = get_blog_articles_collection()

    if collection is None:
        print("Не удалось получить коллекцию статей.")
        return []

    try:
        cursor = collection.find(
            {
                "lang": "en-US",
                "status": "published"
            },
            {
                "_id": 0,
                "title": 1,
                "url_slug": 1,
                "seo_title": 1,
                "seo_description": 1,
                "short_description": 1,
                "lang": 1,
                "status": 1
            }
        )

        articles = []
        for doc in cursor:
            articles.append({
                "title": doc.get("title", "").strip(),
                "url_slug": doc.get("url_slug", "").strip(),
                "seo_title": doc.get("seo_title", "").strip(),
                "seo_description": doc.get("seo_description", "").strip(),
                "short_description": doc.get("short_description", "").strip(),
                "lang": doc.get("lang", "").strip(),
                "status": doc.get("status", "").strip()
            })

        return articles

    except Exception as e:
        print(f"Ошибка при получении статей из MongoDB: {e}")
        return []


def get_existing_article_titles():
    """
    Возвращает только список заголовков существующих статей.
    """
    articles = get_existing_articles()
    return [article["title"] for article in articles if article.get("title")]


def save_existing_articles_locally(articles):
    """
    Сохраняет snapshot существующих статей локально в JSON.
    """
    ensure_output_dir()

    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": len(articles),
        "articles": articles
    }

    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print("Список существующих статей сохранен локально.")
        print(f"Файл: {output_path}")
        return output_path

    except Exception as e:
        print(f"Ошибка при сохранении JSON-файла: {e}")
        return None


def print_existing_articles_preview(limit=20):
    """
    Печатает краткий preview существующих статей.
    """
    articles = get_existing_articles()

    print(f"Найдено published en-US статей: {len(articles)}")

    for i, article in enumerate(articles[:limit], start=1):
        print(f"{i}. {article['title']} | slug: {article['url_slug']}")


def main():
    articles = get_existing_articles()

    if not articles:
        print("Не удалось получить статьи или список пуст.")
        return

    print_existing_articles_preview(limit=20)
    save_existing_articles_locally(articles)


if __name__ == "__main__":
    main()