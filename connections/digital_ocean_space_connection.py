from boto3.session import Session
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from config import spaces


def get_spaces_client():
    """Return a DigitalOcean Spaces client without extra console output."""
    return Session().client(
        service_name="s3",
        region_name=spaces["region"],
        endpoint_url=spaces["endpoint"],
        aws_access_key_id=spaces["key"],
        aws_secret_access_key=spaces["secret"],
        config=Config(signature_version="s3v4"),
    )


def test_spaces_connection() -> bool:
    """Verify access to the configured Spaces bucket without modifying data."""
    bucket = spaces["bucket"]
    try:
        client = get_spaces_client()
        response = client.head_bucket(Bucket=bucket)
        print("DigitalOcean Spaces connection established successfully.")
        print(f"Bucket: {bucket}")
        print(f"Region: {spaces['region']}")
        print(f"Endpoint: {spaces['endpoint']}")
        print(f"HTTP Status: {response['ResponseMetadata']['HTTPStatusCode']}")
        return True
    except NoCredentialsError:
        print("Missing DigitalOcean Spaces credentials.")
        return False
    except EndpointConnectionError as exc:
        print(f"Failed to connect to the Spaces endpoint: {exc}")
        return False
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        error_message = exc.response.get("Error", {}).get("Message", str(exc))
        print("Failed to connect to DigitalOcean Spaces.")
        print(f"Bucket: {bucket}")
        print(f"Error code: {error_code}")
        print(f"Message: {error_message}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected Spaces connection error: {exc}")
        return False


def build_spaces_object_url(object_key: str, use_cdn: bool = True) -> str:
    """Return a public URL for a Spaces object."""
    bucket = spaces["bucket"]
    region = spaces["region"]
    if use_cdn:
        return f"https://{bucket}.{region}.cdn.digitaloceanspaces.com/{object_key}"
    return f"https://{bucket}.{region}.digitaloceanspaces.com/{object_key}"


if __name__ == "__main__":
    test_spaces_connection()
