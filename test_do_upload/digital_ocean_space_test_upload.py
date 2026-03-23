from datetime import datetime, timezone

from boto3.session import Session
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from config import spaces


TEST_OBJECT_KEY = "blog-articles/en/test_article_001/index.mdx"


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


def build_public_urls(object_key: str) -> dict:
    """Return origin and CDN URLs for a Spaces object."""
    bucket = spaces["bucket"]
    region = spaces["region"]
    return {
        "origin_url": f"https://{bucket}.{region}.digitaloceanspaces.com/{object_key}",
        "cdn_url": f"https://{bucket}.{region}.cdn.digitaloceanspaces.com/{object_key}",
    }


def generate_test_mdx() -> str:
    """Generate a temporary MDX payload for upload testing."""
    now_iso = datetime.now(timezone.utc).isoformat()
    return f"""---
title: \"Test Article 001\"
seo_title: \"Test Article 001\"
seo_description: \"Temporary test article uploaded to DigitalOcean Spaces.\"
short_description: \"Temporary test article for upload verification.\"
lang: \"en-US\"
publish_date: \"{now_iso}\"
status: \"test\"
---

# Test Article 001

This is a temporary MDX file uploaded to DigitalOcean Spaces for testing.

- Folder path: `blog-articles/en/test_article_001/`
- File name: `index.mdx`

Uploaded at: `{now_iso}`
"""


def upload_test_mdx() -> bool:
    """Upload a temporary MDX file to Spaces."""
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
        print("Uploaded the test MDX file to DigitalOcean Spaces.")
        print(f"Bucket: {bucket}")
        print(f"Key: {TEST_OBJECT_KEY}")
        print(f"ETag: {response.get('ETag')}")
        print("The file should now be readable.")
        print(f"Origin URL: {urls['origin_url']}")
        print(f"CDN URL: {urls['cdn_url']}")
        return True
    except NoCredentialsError:
        print("Missing DigitalOcean Spaces credentials.")
        return False
    except EndpointConnectionError as exc:
        print(f"Failed to connect to the endpoint: {exc}")
        return False
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        error_message = exc.response.get("Error", {}).get("Message", str(exc))
        print("Failed to upload the test MDX file to Spaces.")
        print(f"Error code: {error_code}")
        print(f"Message: {error_message}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected upload error: {exc}")
        return False


def delete_test_mdx() -> bool:
    """Delete the temporary MDX file from Spaces."""
    bucket = spaces["bucket"]
    try:
        client = get_spaces_client()
        client.delete_object(Bucket=bucket, Key=TEST_OBJECT_KEY)
        print("Deleted the test MDX file from DigitalOcean Spaces.")
        print(f"Bucket: {bucket}")
        print(f"Key: {TEST_OBJECT_KEY}")
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        error_message = exc.response.get("Error", {}).get("Message", str(exc))
        print("Failed to delete the test MDX file from Spaces.")
        print(f"Error code: {error_code}")
        print(f"Message: {error_message}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected deletion error: {exc}")
        return False


def ask_delete_confirmation() -> bool:
    """Ask whether the temporary test file should be deleted."""
    while True:
        answer = input("Delete the test file from Spaces? (yes/no): ").strip().lower()
        if answer in {"yes", "y"}:
            return True
        if answer in {"no", "n"}:
            return False
        print("Please enter 'yes' or 'no'.")


if __name__ == "__main__":
    uploaded = upload_test_mdx()
    if uploaded:
        if ask_delete_confirmation():
            delete_test_mdx()
        else:
            print("The file was left in Spaces for manual inspection.")
