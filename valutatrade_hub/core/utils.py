"""Чтение и безопасная запись JSON-файлов приложения."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

USERS_FILE = DATA_DIR / "users.json"
PORTFOLIOS_FILE = DATA_DIR / "portfolios.json"
RATES_FILE = DATA_DIR / "rates.json"


def load_json(path: Path) -> list | dict:
    """Прочитать список или словарь из JSON-файла."""
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Файл данных '{path}' не найден") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Файл '{path}' содержит некорректный JSON") from error
    except UnicodeDecodeError as error:
        raise ValueError(f"Файл '{path}' должен быть в кодировке UTF-8") from error
    except OSError as error:
        raise OSError(f"Не удалось прочитать файл '{path}': {error}") from error

    if not isinstance(data, (list, dict)):
        raise ValueError(f"Файл '{path}' должен содержать список или объект JSON")

    return data


def save_json(path: Path, data: list | dict) -> None:
    """Сохранить JSON через временный файл и атомарную замену целевого файла."""
    if not isinstance(data, (list, dict)):
        raise TypeError("Данные для сохранения должны быть списком или словарём")

    content = json.dumps(
        data,
        ensure_ascii=False,
        indent=4,
        allow_nan=False,
    )

    temporary_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        # Файл рядом с целевым позволяет заменить его на том же диске.
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            file.write(content + "\n")
        # В Windows временный файл необходимо закрыть перед заменой.
        os.replace(temporary_path, path)
    except OSError as error:
        raise OSError(f"Не удалось записать файл '{path}': {error}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
