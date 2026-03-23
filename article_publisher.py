from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from boto3.session import Session
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from config import spaces
from connections.mongo_connection import get_blog_articles_collection


ARTICLE_META_FILENAME = "article_meta.json"
ARTICLE_MDX_FILENAME = "article.mdx"
ARTICLE_RECORD_FILENAME = "article_record.json"


def load_json_file(file_path: Path) -> Optional[dict]:
    """Load JSON from disk."""
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to read JSON file {file_path}: {exc}")
        return None


def read_text_file(file_path: Path) -> Optional[str]:
    """Load a text file from disk."""
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to read file {file_path}: {exc}")
        return None


def write_json_file(file_path: Path, payload: dict) -> bool:
    """Write JSON to disk."""
    try:
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to write JSON file {file_path}: {exc}")
        return False


def get_spaces_client():
    """Return a DigitalOcean Spaces client."""
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
    """Build the Spaces object key for an article directory."""
    storage_lang_dir = article_dir.parent.name.strip()
    slug = article_dir.name.strip()
    if not storage_lang_dir:
        raise ValueError("Could not determine the storage language directory from the article path.")
    if not slug:
        raise ValueError("Could not determine the article slug from the article path.")
    return f"blog-articles/{storage_lang_dir}/{slug}/index.mdx"


def build_public_urls(object_key: str) -> dict:
    """Build origin and CDN URLs for a Spaces object."""
    bucket = spaces["bucket"]
    region = spaces["region"]
    origin_url = f"https://{bucket}.{region}.digitaloceanspaces.com/{object_key}"
    cdn_base_url = str(spaces.get("cdn_base_url", "")).strip()
    if cdn_base_url:
        cdn_url = f"{cdn_base_url.rstrip('/')}/{object_key}"
    else:
        cdn_url = f"https://{bucket}.{region}.cdn.digitaloceanspaces.com/{object_key}"
    return {"origin_url": origin_url, "cdn_url": cdn_url}


def upload_article_mdx_to_spaces(mdx_content: str, object_key: str) -> Optional[dict]:
    """Upload article MDX to Spaces and return public URLs."""
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
        print("Uploaded the MDX file to DigitalOcean Spaces.")
        print(f"Bucket: {bucket}")
        print(f"Key: {object_key}")
        print(f"ETag: {response.get('ETag')}")
        print(f"Origin URL: {urls['origin_url']}")
        print(f"CDN URL: {urls['cdn_url']}")
        return urls
    except NoCredentialsError:
        print("Missing DigitalOcean Spaces credentials.")
        return None
    except EndpointConnectionError as exc:
        print(f"Failed to connect to the DigitalOcean Spaces endpoint: {exc}")
        return None
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        error_message = exc.response.get("Error", {}).get("Message", str(exc))
        print("Failed to upload the MDX file to Spaces.")
        print(f"Error code: {error_code}")
        print(f"Message: {error_message}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected Spaces upload error: {exc}")
        return None


def delete_object_from_spaces(object_key: str) -> bool:
    """Delete an object from Spaces for rollback purposes."""
    try:
        client = get_spaces_client()
        client.delete_object(Bucket=spaces["bucket"], Key=object_key)
        print(f"Deleted the Spaces object: {object_key}")
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        error_message = exc.response.get("Error", {}).get("Message", str(exc))
        print("Failed to delete the Spaces object during rollback.")
        print(f"Error code: {error_code}")
        print(f"Message: {error_message}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected Spaces deletion error: {exc}")
        return False


def get_existing_article_by_slug(slug: str) -> Optional[dict]:
    """Check whether an article with the given slug already exists in MongoDB."""
    collection = get_blog_articles_collection()
    if collection is None:
        print("Failed to get the blog articles collection.")
        return None
    try:
        return collection.find_one(
            {"url_slug": slug},
            {"_id": 1, "url_slug": 1, "title": 1, "status": 1, "content_url": 1, "img_url": 1},
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to check the slug in MongoDB: {exc}")
        return None


def insert_article_to_mongo(document: dict) -> bool:
    """Insert the published article document into MongoDB."""
    collection = get_blog_articles_collection()
    if collection is None:
        print("Failed to get the blog articles collection.")
        return False
    try:
        result = collection.insert_one(document)
        print("Inserted the article into MongoDB.")
        print(f"Inserted ID: {result.inserted_id}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to insert the article into MongoDB: {exc}")
        return False


def parse_publish_date(value: Optional[str]) -> datetime:
    """Parse an ISO datetime string or fall back to current UTC time."""
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)


def build_article_document(meta: dict, content_url: str) -> dict:
    """Build the MongoDB document expected by the frontend."""
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
    """Update local metadata files after a successful publication."""
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
    """Validate required article metadata fields."""
    errors: list[str] = []
    for field in ["title", "url_slug", "short_description", "seo_title", "seo_description", "lang"]:
        if not str(meta.get(field, "")).strip():
            errors.append(f"Missing required meta field: {field}.")
    return errors


def validate_article_inputs(article_dir: Path, meta: dict, mdx_content: str) -> list[str]:
    """Validate article inputs before publication."""
    errors = validate_meta(meta)
    slug = str(meta.get("url_slug", "")).strip()
    folder_slug = article_dir.name.strip()
    if not folder_slug:
        errors.append("The article directory name is empty.")
    if not slug:
        errors.append("The article_meta.json file does not contain url_slug.")
    if slug and folder_slug and slug != folder_slug:
        errors.append(f"The slug in metadata does not match the article directory name: meta='{slug}', folder='{folder_slug}'.")
    if mdx_content is None or not mdx_content.strip():
        errors.append("The article.mdx file is empty or could not be read.")
    return errors


def publish_article(article_dir: Path) -> dict | None:
    """Publish a prepared article directory to Spaces and MongoDB."""
    article_meta_path = article_dir / ARTICLE_META_FILENAME
    article_mdx_path = article_dir / ARTICLE_MDX_FILENAME
    meta = load_json_file(article_meta_path)
    if meta is None:
        print("Failed to load article_meta.json.")
        return None
    mdx_content = read_text_file(article_mdx_path)
    if mdx_content is None:
        print("Failed to read article.mdx.")
        return None
    validation_errors = validate_article_inputs(article_dir, meta, mdx_content)
    if validation_errors:
        print("Publication stopped because validation failed:")
        for error in validation_errors:
            print(f"- {error}")
        return None
    slug = str(meta["url_slug"]).strip()
    existing_doc = get_existing_article_by_slug(slug)
    if existing_doc:
        print("An article with this slug already exists in MongoDB.")
        print(f"Slug: {slug}")
        print(f"Title: {existing_doc.get('title')}")
        print(f"Status: {existing_doc.get('status')}")
        print(f"Content URL: {existing_doc.get('content_url')}")
        return {"status": "already_exists", "existing_doc": existing_doc}
    object_key = build_spaces_object_key(article_dir)
    upload_result = upload_article_mdx_to_spaces(mdx_content=mdx_content, object_key=object_key)
    if upload_result is None:
        print("Publication stopped because the MDX file could not be uploaded to Spaces.")
        return None
    content_url = upload_result["cdn_url"]
    mongo_document = build_article_document(meta=meta, content_url=content_url)
    inserted = insert_article_to_mongo(mongo_document)
    if not inserted:
        print("MongoDB insert failed. Rolling back the uploaded MDX file from Spaces.")
        delete_object_from_spaces(object_key)
        return None
    update_local_article_files(article_dir=article_dir, meta=meta, content_url=content_url, object_key=object_key)
    print("Publication completed successfully.")
    print(f"Slug: {slug}")
    print(f"Local article directory: {article_dir}")
    print(f"Spaces object key: {object_key}")
    print(f"Content URL: {content_url}")
    return {
        "status": "published",
        "slug": slug,
        "content_url": content_url,
        "object_key": object_key,
        "article_dir": str(article_dir).replace('\\', '/'),
    }
