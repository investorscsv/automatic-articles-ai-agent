from datetime import datetime, timezone
from boto3.session import Session
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError
from config import spaces


TEST_OBJECT_KEY = "blog-articles/en/test_article_001/index.mdx"


def get_spaces_client():
    """Возвращает клиент DigitalOcean Spaces."""
    session = Session()
    return session.client(
        service_name="s3",
        region_name=spaces["region"],
        endpoint_url=spaces["endpoint"],
        aws_access_key_id=spaces["key"],
        aws_secret_access_key=spaces["secret"],
        config=Config(signature_version="s3v4")
    )


def build_public_urls(object_key: str) -> dict:
    """
    Возвращает origin и CDN URL для объекта.
    CDN URL будет работать, если CDN включен для bucket.
    """
    bucket = spaces["bucket"]
    region = spaces["region"]

    return {
        "origin_url": f"https://{bucket}.{region}.digitaloceanspaces.com/{object_key}",
        "cdn_url": f"https://{bucket}.{region}.cdn.digitaloceanspaces.com/{object_key}",
    }


def generate_test_mdx() -> str:
    """Генерирует тестовый MDX-контент."""
    now_iso = datetime.now(timezone.utc).isoformat()

    return f"""---
title: "Test Article 001"
seo_title: "Test Article 001"
seo_description: "Temporary test article uploaded to DigitalOcean Spaces."
short_description: "Temporary test article for upload verification."
lang: "en-US"
publish_date: "{now_iso}"
status: "test"
---

# Test Article 001

This is a temporary MDX file uploaded to DigitalOcean Spaces for testing.

- Folder path: `blog-articles/en/test_article_001/`
- File name: `index.mdx`

Uploaded at: `{now_iso}`
"""


def upload_test_mdx() -> bool:
    """Загружает тестовый MDX-файл в Spaces."""
    bucket = spaces["bucket"]
    content = generate_test_mdx()
    urls = build_public_urls(TEST_OBJECT_KEY)

    try:
        client = get_spaces_client()

        response = client.put_object(
            Bucket=bucket,
            Key=TEST_OBJECT_KEY,
            Body=content.encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
            ACL="public-read",
        )

        print("Тестовый MDX-файл успешно загружен в DigitalOcean Spaces.")
        print(f"Bucket: {bucket}")
        print(f"Key: {TEST_OBJECT_KEY}")
        print(f"ETag: {response.get('ETag')}")
        print("Файл должен быть доступен для чтения.")
        print(f"Origin URL: {urls['origin_url']}")
        print(f"CDN URL: {urls['cdn_url']}")
        print()
        return True

    except NoCredentialsError:
        print("Ошибка: отсутствуют credentials для DigitalOcean Spaces.")
        return False

    except EndpointConnectionError as e:
        print(f"Ошибка подключения к endpoint: {e}")
        return False

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        print("Не удалось загрузить тестовый MDX-файл в Spaces.")
        print(f"Код ошибки: {error_code}")
        print(f"Сообщение: {error_message}")
        return False

    except Exception as e:
        print(f"Неизвестная ошибка при загрузке файла: {e}")
        return False


def delete_test_mdx() -> bool:
    """Удаляет тестовый MDX-файл из Spaces."""
    bucket = spaces["bucket"]

    try:
        client = get_spaces_client()

        client.delete_object(
            Bucket=bucket,
            Key=TEST_OBJECT_KEY
        )

        print("Тестовый MDX-файл успешно удален из DigitalOcean Spaces.")
        print(f"Bucket: {bucket}")
        print(f"Key: {TEST_OBJECT_KEY}")
        return True

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        print("Не удалось удалить тестовый MDX-файл из Spaces.")
        print(f"Код ошибки: {error_code}")
        print(f"Сообщение: {error_message}")
        return False

    except Exception as e:
        print(f"Неизвестная ошибка при удалении файла: {e}")
        return False


def ask_delete_confirmation() -> bool:
    """Спрашивает, нужно ли удалить тестовый файл."""
    while True:
        answer = input("Удалить тестовый файл из Spaces? (yes/no): ").strip().lower()

        if answer in {"yes", "y"}:
            return True
        if answer in {"no", "n"}:
            return False

        print("Пожалуйста, введи 'yes' или 'no'.")


if __name__ == "__main__":
    uploaded = upload_test_mdx()

    if uploaded:
        should_delete = ask_delete_confirmation()

        if should_delete:
            delete_test_mdx()
        else:
            print("Файл оставлен в Spaces. Можешь проверить его вручную.")