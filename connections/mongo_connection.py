from __future__ import annotations

from pymongo import MongoClient

from config import mongo_db


def build_mongo_connection_string() -> str:
    """Build the MongoDB connection string."""
    server = mongo_db["server"]
    login = mongo_db["login"]
    password = mongo_db["password"]
    return f"mongodb+srv://{login}:{password}@{server}/?retryWrites=true&w=majority"


def get_mongo_client() -> MongoClient:
    """Return a MongoDB client instance."""
    return MongoClient(build_mongo_connection_string())


def test_mongo_connection() -> bool:
    """Ping MongoDB and print a human-readable status message."""
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        print("MongoDB connection established successfully.")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to connect to MongoDB: {exc}")
        return False


def get_blog_articles_collection():
    """Return the blog articles collection."""
    client = get_mongo_client()
    db = client[mongo_db["database_blog"]]
    return db[mongo_db["collection_articles"]]


if __name__ == "__main__":
    test_mongo_connection()
