from pymongo import MongoClient
from config import mongo_db


def build_mongo_connection_string():
    """Формирует строку подключения к MongoDB."""
    server = mongo_db["server"]
    login = mongo_db["login"]
    password = mongo_db["password"]

    return f"mongodb+srv://{login}:{password}@{server}/?retryWrites=true&w=majority"


def get_mongo_client():
    """Возвращает MongoClient без вывода в консоль."""
    connection_string = build_mongo_connection_string()
    return MongoClient(connection_string)


def test_mongo_connection():
    """Проверяет подключение к MongoDB и печатает результат."""
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        print("Подключение к MongoDB успешно установлено!")
        return True
    except Exception as e:
        print(f"Не удалось подключиться к MongoDB: {e}")
        return False


def get_blog_articles_collection():
    """Возвращает коллекцию статей блога."""
    client = get_mongo_client()
    db = client[mongo_db["database_blog"]]
    return db[mongo_db["collection_articles"]]


if __name__ == "__main__":
    test_mongo_connection()