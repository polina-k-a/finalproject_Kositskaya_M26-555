"""Работа с JSON-файлами и вспомогательное форматирование сумм."""

import json
import math
import os
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

FIAT_BALANCE_PRECISION = 2
CRYPTO_BALANCE_PRECISION = 4
CRYPTO_CODES = {"BTC", "ETH", "SOL"}


def format_balance(value: float, currency_code: str) -> str:
    """Оформить сумму для вывода, не изменяя сохранённое значение."""
    precision = (
        CRYPTO_BALANCE_PRECISION
        if currency_code in CRYPTO_CODES
        else FIAT_BALANCE_PRECISION
    )
    return f"{value:.{precision}f}"


def validate_rate(value: float, pair: str) -> float:
    """Вернуть положительный конечный курс или сообщить о неверном значении"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Курс {pair} должен быть числом")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Курс {pair} должен быть положительным конечным числом")
    return float(value)


def parse_utc_timestamp(value: str) -> datetime:
    """Прочитать ISO-время; старые даты без часового пояса считать временем UTC."""
    if not isinstance(value, str):
        raise ValueError("Время обновления должно быть строкой ISO")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Некорректное время обновления курса") from error
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def create_json_cache() -> Callable[[Path], list | dict]:
    """Создать замыкание для кеширования чтения неизменившихся JSON-файлов."""
    cached = {}

    def read(path: Path) -> list | dict:
        """Перечитать изменённый файл; вернуть копию для безопасного изменения."""
        stat = path.stat()
        version = (stat.st_mtime_ns, stat.st_size)
        if path not in cached or cached[path][0] != version:
            cached[path] = (version, load_json(path))
        return deepcopy(cached[path][1])

    return read


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
