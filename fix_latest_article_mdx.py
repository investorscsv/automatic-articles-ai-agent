from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional, Tuple


BASE_OUTPUT_DIR = Path("generated_articles/en")


def find_latest_article_meta(base_dir: Path) -> Optional[Path]:
    """Find the most recently modified article_meta.json file."""
    meta_files = list(base_dir.rglob("article_meta.json"))
    if not meta_files:
        return None
    return max(meta_files, key=lambda path: path.stat().st_mtime)


def load_json_file(file_path: Path) -> Optional[dict]:
    """Load JSON from disk."""
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to read JSON file {file_path}: {exc}")
        return None


def read_text_file(file_path: Path) -> Optional[str]:
    """Load a text file from disk."""
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to read file {file_path}: {exc}")
        return None


def write_text_file(file_path: Path, content: str) -> bool:
    """Write a text file to disk."""
    try:
        file_path.write_text(content, encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to write file {file_path}: {exc}")
        return False


def clean_mojibake(text: str) -> str:
    """Replace common mojibake sequences in generated text."""
    replacements = {
        "â€™": "'",
        "â€œ": '"',
        "â€\x9d": '"',
        "â€“": "–",
        "â€”": "—",
        "â€¦": "...",
        "Â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def strip_markdown_fences(text: str) -> str:
    """Remove wrapping markdown fences from generated text."""
    text = text.strip()
    for prefix in ("```mdx", "```markdown", "```md", "```"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def split_frontmatter_and_body(mdx: str) -> Tuple[Optional[str], str]:
    """Return the YAML frontmatter and body, if frontmatter exists."""
    if not mdx.startswith("---\n"):
        return None, mdx
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", mdx, flags=re.DOTALL)
    if not match:
        return None, mdx
    return match.group(1).strip(), match.group(2).strip()


def clean_article_body(body: str) -> str:
    """Clean common model artifacts from an article body."""
    if not body:
        return ""
    body = clean_mojibake(body)
    body = strip_markdown_fences(body)
    body = re.sub(r"\[\d+\]", "", body)
    body = re.sub(r"\[L\d+(?:-L?\d+)?\]", "", body)
    body = re.sub(r"【[^】]+】", "", body)
    lines = body.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    trailing_garbage = {"}", "]", ");", "```"}
    while lines and lines[-1].strip() in trailing_garbage:
        lines.pop()
    while lines and re.fullmatch(r"[}\])>]+", lines[-1].strip()):
        lines.pop()
    body = "\n".join(lines)
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    return body.strip()


def validate_mdx(frontmatter: str | None, body: str) -> list[str]:
    """Run a lightweight validation of an MDX document."""
    errors: list[str] = []
    if frontmatter is not None and not frontmatter.strip():
        errors.append("Frontmatter is empty.")
    if not body.strip():
        errors.append("Article body is empty.")
        return errors
    h2_count = len(re.findall(r"^## ", body, flags=re.MULTILINE))
    faq_h3_count = len(re.findall(r"^### ", body, flags=re.MULTILINE))
    link_count = len(re.findall(r"\[.*?\]\(https?://.*?\)", body))
    if h2_count < 3:
        errors.append(f"Too few H2 sections: {h2_count}.")
    if "## FAQ" not in body:
        errors.append("The FAQ section is missing.")
    if faq_h3_count < 3:
        errors.append(f"Too few FAQ H3 items: {faq_h3_count}.")
    if "## Further reading" not in body:
        errors.append("The Further reading section is missing.")
    if link_count < 3:
        errors.append(f"Too few external links: {link_count}.")
    if body.rstrip().endswith(("}", "]", "```")):
        errors.append("The body ends with trailing service characters.")
    return errors


def fix_latest_article_mdx() -> None:
    """Clean the latest generated article.mdx file in place."""
    latest_meta_path = find_latest_article_meta(BASE_OUTPUT_DIR)
    if latest_meta_path is None:
        print("No article_meta.json files were found.")
        return
    print(f"Found the latest article metadata file: {latest_meta_path}")
    if load_json_file(latest_meta_path) is None:
        print("Failed to load article_meta.json.")
        return
    mdx_path = latest_meta_path.parent / "article.mdx"
    if not mdx_path.exists():
        print(f"article.mdx was not found: {mdx_path}")
        return
    original_mdx = read_text_file(mdx_path)
    if original_mdx is None:
        print("Failed to read article.mdx.")
        return
    old_frontmatter, old_body = split_frontmatter_and_body(original_mdx)
    if old_frontmatter is None:
        print("Frontmatter was not found. Only the article body will be cleaned.")
        old_body = original_mdx
    new_body = clean_article_body(old_body)
    final_mdx = f"{new_body}\n"
    errors = validate_mdx(old_frontmatter, new_body)
    changed = final_mdx != original_mdx
    if changed:
        backup_path = mdx_path.with_suffix(".mdx.bak")
        if write_text_file(backup_path, original_mdx):
            print(f"Created backup: {backup_path}")
        if write_text_file(mdx_path, final_mdx):
            print(f"Updated article.mdx: {mdx_path}")
        else:
            print("Failed to write the updated article.mdx file.")
            return
    else:
        print("No changes were required. article.mdx already looks clean.")
    if errors:
        print("\nMDX validation warnings:")
        for error in errors:
            print(f"- {error}")
    else:
        print("\nMDX passed the basic validation checks.")
    print("\nDone.")


if __name__ == "__main__":
    fix_latest_article_mdx()
