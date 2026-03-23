import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from boto3.session import Session
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from config import spaces
from connections.mongo_connection import get_blog_articles_collection


BASE_OUTPUT_DIR = Path("generated_articles/en")
ARTICLE_META_FILENAME = "article_meta.json"
ARTICLE_MDX_FILENAME = "article.mdx"
ARTICLE_RECORD_FILENAME = "article_record.json"


def find_latest_article_meta(base_dir: Path) -> Optional[Path]:
    """
    Находит самый свежий article_meta.json по времени модификации.
    """
    meta_files = list(base_dir.rglob(ARTICLE_META_FILENAME))
    if not meta_files:
        return None

    return max(meta_files, key=lambda p: p.stat().st_mtime)


def load_json_file(file_path: Path) -> Optional[dict]:
    """
    Загружает JSON-файл и возвращает dict.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка чтения JSON {file_path}: {e}")
        return None


def read_text_file(file_path: Path) -> Optional[str]:
    """
    Читает текстовый файл и возвращает его содержимое.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Ошибка чтения файла {file_path}: {e}")
        return None


def write_json_file(file_path: Path, payload: dict) -> bool:
    """
    Безопасно записывает dict в JSON-файл.
    """
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Ошибка записи JSON {file_path}: {e}")
        return False


def get_spaces_client():
    """
    Возвращает клиент DigitalOcean Spaces.
    """
    session = Session()
    return session.client(
        service_name="s3",
        region_name=spaces["region"],
        endpoint_url=spaces["endpoint"],
        aws_access_key_id=spaces["key"],
        aws_secret_access_key=spaces["secret"],
        config=Config(signature_version="s3v4"),
    )


def build_spaces_object_key(article_dir: Path) -> str:
    """
    Строит путь в DigitalOcean Spaces на основе реальной локальной папки статьи.

    Пример:
    generated_articles/en/my-article-slug
    -> blog-articles/en/my-article-slug/index.mdx
    """
    storage_lang_dir = article_dir.parent.name.strip()
    slug = article_dir.name.strip()

    if not storage_lang_dir:
        raise ValueError("Не удалось определить storage language dir из пути статьи.")

    if not slug:
        raise ValueError("Не удалось определить slug из пути статьи.")

    return f"blog-articles/{storage_lang_dir}/{slug}/index.mdx"


def build_public_urls(object_key: str) -> dict:
    """
    Возвращает public URL для объекта.
    Приоритет:
    1. spaces['cdn_base_url'] если задан
    2. стандартный CDN URL bucket.region.cdn.digitaloceanspaces.com
    3. origin URL
    """
    bucket = spaces["bucket"]
    region = spaces["region"]

    origin_url = f"https://{bucket}.{region}.digitaloceanspaces.com/{object_key}"

    cdn_base_url = str(spaces.get("cdn_base_url", "")).strip()
    if cdn_base_url:
        cdn_base_url = cdn_base_url.rstrip("/")
        cdn_url = f"{cdn_base_url}/{object_key}"
    else:
        cdn_url = f"https://{bucket}.{region}.cdn.digitaloceanspaces.com/{object_key}"

    return {
        "origin_url": origin_url,
        "cdn_url": cdn_url,
    }


def upload_article_mdx_to_spaces(mdx_content: str, object_key: str) -> Optional[dict]:
    """
    Загружает article.mdx в Spaces как index.mdx.
    Возвращает словарь с URL-ами или None.
    """
    bucket = spaces["bucket"]
    urls = build_public_urls(object_key)

    try:
        client = get_spaces_client()

        response = client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=mdx_content.encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
            ACL="public-read",
        )

        print("MDX-файл успешно загружен в DigitalOcean Spaces.")
        print(f"Bucket: {bucket}")
        print(f"Key: {object_key}")
        print(f"ETag: {response.get('ETag')}")
        print(f"Origin URL: {urls['origin_url']}")
        print(f"CDN URL: {urls['cdn_url']}")

        return urls

    except NoCredentialsError:
        print("Ошибка: отсутствуют credentials для DigitalOcean Spaces.")
        return None

    except EndpointConnectionError as e:
        print(f"Ошибка подключения к endpoint DigitalOcean Spaces: {e}")
        return None

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        print("Не удалось загрузить MDX-файл в Spaces.")
        print(f"Код ошибки: {error_code}")
        print(f"Сообщение: {error_message}")
        return None

    except Exception as e:
        print(f"Неизвестная ошибка при загрузке файла в Spaces: {e}")
        return None


def delete_object_from_spaces(object_key: str) -> bool:
    """
    Удаляет объект из Spaces. Используется для rollback.
    """
    bucket = spaces["bucket"]

    try:
        client = get_spaces_client()
        client.delete_object(Bucket=bucket, Key=object_key)
        print(f"Файл удален из Spaces: {object_key}")
        return True

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        print("Не удалось удалить файл из Spaces во время rollback.")
        print(f"Код ошибки: {error_code}")
        print(f"Сообщение: {error_message}")
        return False

    except Exception as e:
        print(f"Неизвестная ошибка при удалении файла из Spaces: {e}")
        return False


def get_existing_article_by_slug(slug: str) -> Optional[dict]:
    """
    Проверяет в MongoDB, существует ли уже статья с таким slug.
    """
    collection = get_blog_articles_collection()

    if collection is None:
        print("Не удалось получить коллекцию статей.")
        return None

    try:
        return collection.find_one(
            {"url_slug": slug},
            {"_id": 1, "url_slug": 1, "title": 1, "status": 1, "content_url": 1},
        )
    except Exception as e:
        print(f"Ошибка при проверке slug в MongoDB: {e}")
        return None


def insert_article_to_mongo(document: dict) -> bool:
    """
    Добавляет статью в MongoDB.
    """
    collection = get_blog_articles_collection()

    if collection is None:
        print("Не удалось получить коллекцию статей.")
        return False

    try:
        result = collection.insert_one(document)
        print("Статья успешно добавлена в MongoDB.")
        print(f"Inserted ID: {result.inserted_id}")
        return True
    except Exception as e:
        print(f"Ошибка при вставке статьи в MongoDB: {e}")
        return False


def parse_publish_date(value: Optional[str]) -> datetime:
    """
    Преобразует ISO-строку в datetime с timezone.
    При ошибке возвращает текущее UTC-время.
    """
    if not value:
        return datetime.now(timezone.utc)

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def build_article_document(meta: dict, content_url: str) -> dict:
    """
    Собирает Mongo-документ в формате, который ожидает фронт.
    """
    return {
        "url_slug": str(meta.get("url_slug", "")).strip(),
        "content_url": content_url,
        "publish_date": parse_publish_date(meta.get("publish_date")),
        "alternative_urls": meta.get("alternative_urls", [""]) or [""],
        "title": str(meta.get("title", "")).strip(),
        "short_description": str(meta.get("short_description", "")).strip(),
        "seo_title": str(meta.get("seo_title", "")).strip(),
        "seo_description": str(meta.get("seo_description", "")).strip(),
        "img_url": str(meta.get("img_url", "")).strip(),
        "status": "published",
        "lang": str(meta.get("lang", "en-US")).strip(),
    }


def update_local_article_files(article_dir: Path, meta: dict, content_url: str, object_key: str) -> None:
    """
    Обновляет локальные article_meta.json и article_record.json после успешной публикации.
    """
    article_meta_path = article_dir / ARTICLE_META_FILENAME
    article_record_path = article_dir / ARTICLE_RECORD_FILENAME

    updated_meta = dict(meta)
    updated_meta["status"] = "published"
    updated_meta["content_url"] = content_url

    if not updated_meta.get("publish_date"):
        updated_meta["publish_date"] = datetime.now(timezone.utc).isoformat()

    write_json_file(article_meta_path, updated_meta)

    existing_record = load_json_file(article_record_path) or {}

    updated_record = {
        "title": updated_meta.get("title", ""),
        "url_slug": updated_meta.get("url_slug", ""),
        "content_url": content_url,
        "publish_date": updated_meta.get("publish_date", ""),
        "alternative_urls": existing_record.get("alternative_urls", [""]),
        "short_description": updated_meta.get("short_description", ""),
        "seo_title": updated_meta.get("seo_title", ""),
        "seo_description": updated_meta.get("seo_description", ""),
        "img_url": updated_meta.get("img_url", ""),
        "status": "published",
        "lang": updated_meta.get("lang", "en-US"),
        "internal_meta": {
            "provider": existing_record.get("internal_meta", {}).get("provider", "novita"),
            "model": existing_record.get("internal_meta", {}).get("model", ""),
            "published_at": datetime.now(timezone.utc).isoformat(),
            "spaces_object_key": object_key,
            "local_article_dir": str(article_dir).replace("\\", "/"),
        },
    }

    write_json_file(article_record_path, updated_record)


def validate_meta(meta: dict) -> list[str]:
    """
    Базовая проверка article_meta.json.
    """
    errors = []

    required_fields = [
        "title",
        "url_slug",
        "short_description",
        "seo_title",
        "seo_description",
        "lang",
    ]

    for field in required_fields:
        if not str(meta.get(field, "")).strip():
            errors.append(f"Отсутствует обязательное поле meta: {field}")

    return errors


def validate_article_inputs(article_dir: Path, meta: dict, mdx_content: str) -> list[str]:
    """
    Комплексная проверка перед публикацией.
    """
    errors = []

    errors.extend(validate_meta(meta))

    slug = str(meta.get("url_slug", "")).strip()
    folder_slug = article_dir.name.strip()

    if not folder_slug:
        errors.append("Имя папки статьи пустое.")

    if not slug:
        errors.append("В article_meta.json отсутствует url_slug.")

    if slug and folder_slug and slug != folder_slug:
        errors.append(
            f"Slug в meta не совпадает с именем папки статьи: meta='{slug}', folder='{folder_slug}'"
        )

    if mdx_content is None or not mdx_content.strip():
        errors.append("Файл article.mdx пустой или не прочитан.")

    return errors


def publish_latest_article() -> None:
    latest_meta_path = find_latest_article_meta(BASE_OUTPUT_DIR)
    if latest_meta_path is None:
        print("Не найден ни один article_meta.json.")
        return

    article_dir = latest_meta_path.parent
    article_meta_path = article_dir / ARTICLE_META_FILENAME
    article_mdx_path = article_dir / ARTICLE_MDX_FILENAME

    print(f"Найдена последняя статья: {article_dir}")

    meta = load_json_file(article_meta_path)
    if meta is None:
        print("Не удалось загрузить article_meta.json.")
        return

    mdx_content = read_text_file(article_mdx_path)
    if mdx_content is None:
        print("Не удалось прочитать article.mdx.")
        return

    validation_errors = validate_article_inputs(article_dir, meta, mdx_content)
    if validation_errors:
        print("Невозможно опубликовать статью. Ошибки:")
        for err in validation_errors:
            print(f"- {err}")
        return

    slug = str(meta["url_slug"]).strip()

    existing_doc = get_existing_article_by_slug(slug)
    if existing_doc:
        print("Статья с таким slug уже существует в MongoDB.")
        print(f"Slug: {slug}")
        print(f"Title: {existing_doc.get('title')}")
        print(f"Status: {existing_doc.get('status')}")
        print(f"Content URL: {existing_doc.get('content_url')}")
        return

    try:
        object_key = build_spaces_object_key(article_dir)
    except ValueError as e:
        print(f"Ошибка построения object_key: {e}")
        return

    upload_result = upload_article_mdx_to_spaces(
        mdx_content=mdx_content,
        object_key=object_key,
    )
    if upload_result is None:
        print("Публикация остановлена: не удалось загрузить файл в Spaces.")
        return

    content_url = upload_result["cdn_url"]
    mongo_document = build_article_document(meta=meta, content_url=content_url)

    inserted = insert_article_to_mongo(mongo_document)
    if not inserted:
        print("Mongo insert не удался. Пытаюсь выполнить rollback: удалить загруженный MDX из Spaces.")
        delete_object_from_spaces(object_key)
        print("Публикация остановлена.")
        return

    update_local_article_files(
        article_dir=article_dir,
        meta=meta,
        content_url=content_url,
        object_key=object_key,
    )

    print()
    print("Публикация завершена успешно.")
    print(f"Slug: {slug}")
    print(f"Local article dir: {article_dir}")
    print(f"Spaces object key: {object_key}")
    print(f"Content URL: {content_url}")


if __name__ == "__main__":
    publish_latest_article()