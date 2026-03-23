from openai import OpenAI

from config import novita


def get_novita_client() -> OpenAI:
    """Return an OpenAI-compatible client configured for Novita."""
    return OpenAI(
        base_url=novita["base_url"],
        api_key=novita["api_key"],
    )


def test_novita_connection() -> bool:
    """Run a lightweight completion call to verify Novita connectivity."""
    try:
        client = get_novita_client()
        response = client.chat.completions.create(
            model=novita["model"],
            messages=[
                {"role": "system", "content": "You are a concise assistant."},
                {"role": "user", "content": "Reply with exactly: Novita connection successful."},
            ],
            temperature=0,
            max_tokens=30,
        )
        text = response.choices[0].message.content
        print("Novita connection established successfully.")
        print(f"Model: {novita['model']}")
        print("Model response:")
        print(text)
        return True
    except Exception as exc:  # noqa: BLE001
        print("Failed to connect to Novita.")
        print(f"Error: {exc}")
        return False


if __name__ == "__main__":
    test_novita_connection()
