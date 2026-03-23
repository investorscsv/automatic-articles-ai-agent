from boto3.session import Session
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError
from config import spaces


def get_spaces_client():
    """Возвращает клиент DigitalOcean Spaces без вывода в консоль."""
    return Session().client(
        service_name="s3",
        region_name=spaces["region"],
        endpoint_url=spaces["endpoint"],
        aws_access_key_id=spaces["key"],
        aws_secret_access_key=spaces["secret"],
        config=Config(signature_version="s3v4")
    )


def test_spaces_connection():
    """
    Проверяет подключение к DigitalOcean Spaces без записи/изменения данных.
    Пытается получить метаданные бакета.
    """
    bucket = spaces["bucket"]

    try:
        client = get_spaces_client()
        response = client.head_bucket(Bucket=bucket)

        print("Подключение к DigitalOcean Spaces успешно установлено!")
        print(f"Bucket: {bucket}")
        print(f"Region: {spaces['region']}")
        print(f"Endpoint: {spaces['endpoint']}")
        print(f"HTTP Status: {response['ResponseMetadata']['HTTPStatusCode']}")
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

        print("Не удалось подключиться к DigitalOcean Spaces.")
        print(f"Bucket: {bucket}")
        print(f"Код ошибки: {error_code}")
        print(f"Сообщение: {error_message}")
        return False

    except Exception as e:
        print(f"Неизвестная ошибка при подключении к Spaces: {e}")
        return False


def build_spaces_object_url(object_key: str, use_cdn: bool = True) -> str:
    """
    Возвращает публичный URL объекта в DigitalOcean Spaces.

    :param object_key: Ключ объекта в бакете
    :param use_cdn: Если True, используется CDN URL
    """
    bucket = spaces["bucket"]
    region = spaces["region"]

    if use_cdn:
        return f"https://{bucket}.{region}.cdn.digitaloceanspaces.com/{object_key}"

    return f"https://{bucket}.{region}.digitaloceanspaces.com/{object_key}"


if __name__ == "__main__":
    test_spaces_connection()