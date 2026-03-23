from openai import OpenAI
from config import novita


def get_novita_client():
    """Возвращает клиент Novita через OpenAI-compatible API без вывода в консоль."""
    return OpenAI(
        base_url=novita["base_url"],
        api_key=novita["api_key"],
    )


def test_novita_connection():
    """Проверяет подключение к Novita и печатает ответ модели."""
    try:
        client = get_novita_client()

        response = client.chat.completions.create(
            model=novita["model"],
            messages=[
                {
                    "role": "system",
                    "content": "You are a concise assistant."
                },
                {
                    "role": "user",
                    "content": "Reply with exactly: Novita connection successful."
                }
            ],
            temperature=0,
            max_tokens=30
        )

        text = response.choices[0].message.content

        print("Подключение к Novita успешно установлено!")
        print(f"Model: {novita['model']}")
        print("Ответ модели:")
        print(text)

        return True

    except Exception as e:
        print("Не удалось подключиться к Novita.")
        print(f"Ошибка: {e}")
        return False


if __name__ == "__main__":
    test_novita_connection()