import os
from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise ValueError(f"Environment variable '{name}' is required but not set")
    return value


mongo_db = {
    "server": get_env("MONGO_SERVER", required=True),
    "database_investors": "investors",
    "database_deals": "deals",
    "database_blog": "blog",
    "login": get_env("MONGO_LOGIN", "inv"),
    "password": get_env("MONGO_PASSWORD", required=True),
    "collection_investors": "investors",
    "collection_deals": "deals",
    "collection_articles": "articles-cdn",
}

spaces = {
    "region": "nyc3",
    "bucket": "crino-cdn",
    "key": get_env("SPACES_KEY", required=True),
    "secret": get_env("SPACES_SECRET", required=True),
    "endpoint": "https://nyc3.digitaloceanspaces.com",
}

novita = {
    "api_key": get_env("NOVITA_API_KEY", required=True),
    "base_url": "https://api.novita.ai/openai",
    "model": "deepseek/deepseek-v3.2",
    "image_model": "flux-2-dev",
}