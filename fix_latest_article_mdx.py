import json
import os
import re
from pathlib import Path
from typing import Optional, Tuple


BASE_OUTPUT_DIR = Path("generated_articles/en")


def find_latest_article_meta(base_dir: Path) -> Optional[Path]:
    """
    Находит самый свежий article_meta.json по времени модификации.
    """
    meta_files = list(base_dir.rglob("article_meta.json"))
    if not meta_files:
        return None

    return max(meta_files, key=lambda p: p.stat().st_mtime)


def load_json_file(file_path: Path) -> Optional[dict]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка чтения JSON {file_path}: {e}")
        return None


def read_text_file(file_path: Path) -> Optional[str]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Ошибка чтения файла {file_path}: {e}")
        return None


def write_text_file(file_path: Path, content: str) -> bool:
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Ошибка записи файла {file_path}: {e}")
        return False


def yaml_escape(value: str) -> str:
    value = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    return value


def normalize_slug(slug: str) -> str:
    slug = (slug or "").strip().lower()
    slug = re.sub(r"[^a-z0-9 -]", "", slug)
    slug = slug.replace(" ", "-")
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    return slug


def clean_mojibake(text: str) -> str:
    replacements = {
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
        "â€“": "–",
        "â€”": "—",
        "â€¦": "...",
        "Â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def strip_markdown_fences(text: str) -> str:
    text = text.strip()

    if text.startswith("```mdx"):
        text = text[len("```mdx"):].strip()
    elif text.startswith("```markdown"):
        text = text[len("```markdown"):].strip()
    elif text.startswith("```md"):
        text = text[len("```md"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    return text


def split_frontmatter_and_body(mdx: str) -> Tuple[Optional[str], str]:
    """
    Возвращает (frontmatter, body).
    Если frontmatter не найден, вернет (None, original_text).
    """
    if not mdx.startswith("---\n"):
        return None, mdx

    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", mdx, flags=re.DOTALL)
    if not match:
        return None, mdx

    frontmatter = match.group(1).strip()
    body = match.group(2).strip()
    return frontmatter, body


def build_frontmatter_from_meta(meta: dict) -> str:
    title = (meta.get("title") or "").strip()
    slug = normalize_slug(meta.get("url_slug") or "")
    seo_title = (meta.get("seo_title") or title).strip()
    seo_description = (meta.get("seo_description") or "").strip()
    short_description = (meta.get("short_description") or "").strip()
    lang = (meta.get("lang") or "en-US").strip()
    status = (meta.get("status") or "draft").strip()
    publish_date = (meta.get("publish_date") or "").strip()
    primary_keyword = (meta.get("primary_keyword") or "").strip()
    secondary_keywords = meta.get("secondary_keywords") or []

    lines = [
        "---",
        f'title: "{yaml_escape(title)}"',
        f'slug: "{yaml_escape(slug)}"',
        f'seo_title: "{yaml_escape(seo_title)}"',
        f'seo_description: "{yaml_escape(seo_description)}"',
        f'short_description: "{yaml_escape(short_description)}"',
        f'lang: "{yaml_escape(lang)}"',
        f'status: "{yaml_escape(status)}"',
        f'publish_date: "{yaml_escape(publish_date)}"',
        f'primary_keyword: "{yaml_escape(primary_keyword)}"',
        "secondary_keywords:",
    ]

    for keyword in secondary_keywords:
        lines.append(f'  - "{yaml_escape(str(keyword).strip())}"')

    lines.append("---")
    return "\n".join(lines)


def clean_article_body(body: str) -> str:
    """
    Чистит body статьи от типового мусора модели.
    """
    if not body:
        return ""

    body = clean_mojibake(body)
    body = strip_markdown_fences(body)

    body = re.sub(r"\[\d+\]", "", body)
    body = re.sub(r"\[L\d+(?:-L?\d+)?\]", "", body)
    body = re.sub(r"【[^】]+】", "", body)

    lines = body.splitlines()

    # удаляем хвостовые пустые строки
    while lines and not lines[-1].strip():
        lines.pop()

    # удаляем очевидный мусор в конце
    trailing_garbage = {"}", "]", ");", "```"}
    while lines and lines[-1].strip() in trailing_garbage:
        lines.pop()

    # удаляем одиночные мусорные хвосты
    while lines and re.fullmatch(r"[}\])>]+", lines[-1].strip()):
        lines.pop()

    body = "\n".join(lines)

    # нормализация пустых строк
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = re.sub(r"[ \t]+\n", "\n", body)

    return body.strip()


def validate_mdx(frontmatter: str, body: str) -> list[str]:
    errors = []

    if frontmatter is not None and not frontmatter.strip():
        errors.append("Frontmatter пустой.")

    if not body.strip():
        errors.append("Body статьи пустой.")
        return errors

    h2_count = len(re.findall(r"^## ", body, flags=re.MULTILINE))
    faq_h3_count = len(re.findall(r"^### ", body, flags=re.MULTILINE))
    link_count = len(re.findall(r"\[.*?\]\(https?://.*?\)", body))

    if h2_count < 3:
        errors.append(f"Слишком мало H2 секций: {h2_count}")

    if "## FAQ" not in body:
        errors.append("Отсутствует секция FAQ.")

    if faq_h3_count < 3:
        errors.append(f"Слишком мало H3 FAQ-вопросов: {faq_h3_count}")

    if "## Further reading" not in body:
        errors.append("Отсутствует секция Further reading.")

    if link_count < 3:
        errors.append(f"Слишком мало внешних ссылок: {link_count}")

    if body.rstrip().endswith(("}", "]", "```")):
        errors.append("Body заканчивается лишним служебным символом.")

    return errors


def fix_latest_article_mdx() -> None:
    latest_meta_path = find_latest_article_meta(BASE_OUTPUT_DIR)
    if latest_meta_path is None:
        print("Не найден ни один article_meta.json.")
        return

    print(f"Найден latest article_meta.json: {latest_meta_path}")

    meta = load_json_file(latest_meta_path)
    if meta is None:
        print("Не удалось загрузить article_meta.json.")
        return

    mdx_path = latest_meta_path.parent / "article.mdx"
    if not mdx_path.exists():
        print(f"Файл article.mdx не найден: {mdx_path}")
        return

    original_mdx = read_text_file(mdx_path)
    if original_mdx is None:
        print("Не удалось прочитать article.mdx.")
        return

    old_frontmatter, old_body = split_frontmatter_and_body(original_mdx)

    if old_frontmatter is None:
        print("Frontmatter не найден. Будет очищено только содержимое статьи.")
        old_body = original_mdx

    new_body = clean_article_body(old_body)
    final_mdx = f"{new_body}\n"

    errors = validate_mdx("", new_body)

    changed = final_mdx != original_mdx

    if changed:
        backup_path = mdx_path.with_suffix(".mdx.bak")
        if write_text_file(backup_path, original_mdx):
            print(f"Создан backup: {backup_path}")

        if write_text_file(mdx_path, final_mdx):
            print(f"article.mdx исправлен: {mdx_path}")
        else:
            print("Не удалось записать исправленный article.mdx.")
            return
    else:
        print("Изменения не потребовались: article.mdx уже выглядит нормально.")

    if errors:
        print("\nЗамечания по структуре MDX:")
        for err in errors:
            print(f"- {err}")
    else:
        print("\nMDX прошел базовую проверку структуры.")

    print("\nГотово.")


if __name__ == "__main__":
    fix_latest_article_mdx()