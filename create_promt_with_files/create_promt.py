from pathlib import Path

# Define the files that should be combined into the prompt bundle.
FILES_TO_COPY = [
    "../existing_articles_service.py",
    "../topic_generator.py",
    "../article_generator.py",
    "../fix_latest_article_mdx.py",
    "../article_publisher.py",
    "../image_creation/generate_image_ai.py",
    "../image_creation/make_final_cover.py",
]

# Define the destination file name.
OUTPUT_FILE = "promt.txt"


def collect_files_to_prompt(files: list[str], output_file: str) -> None:
    """Combine the selected files into one text bundle."""
    output_lines: list[str] = []
    for file_path_str in files:
        file_path = Path(file_path_str)
        output_lines.append("=" * 80)
        output_lines.append(f"FILE: {file_path}")
        output_lines.append("=" * 80)
        if not file_path.exists():
            output_lines.append("ERROR: file not found.\n")
            continue
        if not file_path.is_file():
            output_lines.append("ERROR: path is not a file.\n")
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            output_lines.append("ERROR: failed to read the file as UTF-8.\n")
            continue
        except Exception as exc:  # noqa: BLE001
            output_lines.append(f"ERROR while reading the file: {exc}\n")
            continue
        output_lines.append(content)
        output_lines.append("\n")
    Path(output_file).write_text("\n".join(output_lines), encoding="utf-8")
    print(f"Done. Wrote the bundled file to: {output_file}")


if __name__ == "__main__":
    collect_files_to_prompt(FILES_TO_COPY, OUTPUT_FILE)
