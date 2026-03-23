from pymongo import MongoClient
from config import mongo_db
import re
from bs4 import BeautifulSoup, NavigableString, Tag


def get_mongo_client():
    """Возвращает MongoClient с установленным подключением."""
    server = mongo_db['server']
    login = mongo_db['login']
    password = mongo_db['password']

    connection_string = f"mongodb+srv://{login}:{password}@{server}/?retryWrites=true&w=majority"

    try:
        client = MongoClient(connection_string)
        client.admin.command('ping')
        print("Подключение к MongoDB успешно установлено!")
        return client
    except Exception as e:
        print(f"Не удалось подключиться к MongoDB: {e}")
        return None


def process_paragraph_with_links(tag):
    """
    Обрабатывает параграф, цитату или элемент списка с текстом, ссылками и жирным текстом.
    """
    children = []
    current_text = ""

    punctuation_regex = r"^[.,;!?)]"  # Регулярка для знаков препинания в начале строки

    def append_text_if_any():
        """Добавляет накопленный текст в children с учётом пробелов."""
        nonlocal current_text
        if current_text:
            children.append({"type": "text", "text": current_text})
            current_text = ""

    for elem in tag.children:
        if isinstance(elem, NavigableString):
            text = elem.strip()
            if text:
                # Проверка на пробел перед текстом, если предыдущий элемент ссылка или жирный текст
                if children and children[-1]["type"] in ["link", "strong"] and not re.match(punctuation_regex, text):
                    current_text += " "
                current_text += text
        elif isinstance(elem, Tag):
            if elem.name == 'a':
                append_text_if_any()
                link_text = elem.get_text(strip=True)
                link_url = elem.get('href', '')
                children.append({"type": "link", "text": link_text, "url": link_url})
                current_text = ""
            elif elem.name in ['strong', 'b']:
                append_text_if_any()
                bold_text = elem.get_text(strip=True)
                # Добавляем пробел перед жирным текстом
                if children and children[-1]["type"] == "text" and not children[-1]["text"].endswith(" "):
                    children[-1]["text"] += " "
                elif current_text and not current_text.endswith(" "):
                    current_text += " "
                children.append({"type": "strong", "text": bold_text})
                current_text = " "  # Готовим пробел после жирного текста
            elif elem.name == 'img':
                append_text_if_any()
                img_src = elem.get('src', '')
                if img_src:
                    children.append({"type": "image", "src": img_src})
            elif elem.name == 'blockquote':
                append_text_if_any()
                quote_text = elem.get_text(strip=True)
                children.append({"type": "quote", "text": quote_text})

    append_text_if_any()
    return {"type": "p", "children": children}


def process_list(list_tag):
    """
    Обрабатывает <ul> или <ol> и возвращает массив пунктов списка.
    """
    list_type = "ul" if list_tag.name == 'ul' else "ol"
    items = []
    for li in list_tag.find_all('li', recursive=False):
        items.append(process_paragraph_with_links(li))  # Каждый li обрабатываем как параграф

    return {"type": list_type, "items": items}


def parse_html_to_content(html_str):
    """Парсит HTML и возвращает массив структурированных элементов."""
    soup = BeautifulSoup(html_str, 'html.parser')
    heading_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
    content = []

    for el in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'iframe', 'blockquote', 'img']):
        if el.name in heading_tags:
            content.append({"type": el.name, "text": el.get_text(strip=True)})
        elif el.name == 'p':
            content.append(process_paragraph_with_links(el))
        elif el.name in ['ul', 'ol']:
            content.append({"type": el.name, "items": [process_paragraph_with_links(li) for li in el.find_all('li')]})
        elif el.name == 'iframe':
            content.append({
                "type": "iframe",
                "src": el.get('src', ''),
                "width": el.get('width', '100%'),
                "height": el.get('height', '400px')
            })
        elif el.name == 'img':
            content.append({"type": "image", "src": el.get('src', '')})
        elif el.name == 'blockquote':
            # Добавляем цитату с обработкой вложенных пробелов
            content.append({"type": "quote", "text": el.get_text(strip=True)})

    return clean_extra_spaces(content)

def clean_extra_spaces(content):
    """
    Проходит по всем текстовым узлам и убирает двойные пробелы.
    """
    for item in content:
        if item["type"] == "p" and "children" in item:
            for child in item["children"]:
                if child["type"] == "text":
                    child["text"] = re.sub(r'\s+', ' ', child["text"])
        elif item["type"] == "text" or item["type"] == "quote":
            item["text"] = re.sub(r'\s+', ' ', item["text"])
        elif item["type"] in ["ul", "ol"] and "items" in item:
            clean_extra_spaces(item["items"])
    return content


if __name__ == "__main__":
    slug = "essential-guide-finding-the-right-investor"  # Задайте нужный slug

    # Читаем html из txt-файла
    with open('article_body.txt', 'r', encoding='utf-8') as f:
        html_data = f.read()

    # Парсим html
    content_data = parse_html_to_content(html_data)

    # Очистка от двойных пробелов
    content_data = clean_extra_spaces(content_data)

    # Подключаемся к MongoDB
    client = get_mongo_client()
    if client is not None:
        db = client['blog']
        articles_collection = db['articles']

        # Обновляем поле content для документа с указанным slug
        result = articles_collection.update_one(
            {"url_slug": slug},
            {"$set": {"content": content_data}}
        )

        if result.modified_count > 0:
            print("Поле 'content' успешно заменено!")
        else:
            print("Документ не найден или поле 'content' осталось без изменений.")