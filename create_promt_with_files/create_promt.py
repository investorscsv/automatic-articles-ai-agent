from pathlib import Path

# Укажи здесь список файлов, которые нужно собрать
FILES_TO_COPY = [
    "../existing_articles_service.py",
    "../topic_generator.py",
    "../article_generator.py",
    "../fix_latest_article_mdx.py",
    "../article_publisher.py",
    "../image_creation/generate_image_ai.py",
    "../image_creation/make_final_cover.py"
]

# Имя итогового файла
OUTPUT_FILE = "promt.txt"


def collect_files_to_prompt(files: list[str], output_file: str) -> None:
    output_lines = []

    for file_path_str in files:
        file_path = Path(file_path_str)

        output_lines.append("=" * 80)
        output_lines.append(f"ФАЙЛ: {file_path}")
        output_lines.append("=" * 80)

        if not file_path.exists():
            output_lines.append("ОШИБКА: файл не найден.\n")
            continue

        if not file_path.is_file():
            output_lines.append("ОШИБКА: это не файл.\n")
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            output_lines.append("ОШИБКА: не удалось прочитать файл в UTF-8.\n")
            continue
        except Exception as e:
            output_lines.append(f"ОШИБКА при чтении файла: {e}\n")
            continue

        output_lines.append(content)
        output_lines.append("\n")

    Path(output_file).write_text("\n".join(output_lines), encoding="utf-8")
    print(f"Готово. Все данные записаны в файл: {output_file}")


if __name__ == "__main__":
    collect_files_to_prompt(FILES_TO_COPY, OUTPUT_FILE)