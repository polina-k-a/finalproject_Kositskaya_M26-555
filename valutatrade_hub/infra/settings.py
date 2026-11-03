"""Единая загрузка и кеширование конфигурации приложения."""

import logging
import math
import time
import tomllib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "pyproject.toml"

USERS_FILE_KEY = "users_file"
PORTFOLIOS_FILE_KEY = "portfolios_file"
RATES_FILE_KEY = "rates_file"
LOGS_DIR_KEY = "logs_dir"

PATH_SETTINGS = (
    USERS_FILE_KEY,
    PORTFOLIOS_FILE_KEY,
    RATES_FILE_KEY,
    LOGS_DIR_KEY,
)
POSITIVE_INTEGER_SETTINGS = ("rates_ttl_seconds", "log_max_bytes")
DEFAULT_ACTIONS_LOG_FILENAME = "actions.log"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"
ALLOWED_LOG_LEVELS = ("INFO", "DEBUG")


class SettingsLoader:
    """Загрузчик секции [tool.valutatrade], общий для одного процесса"""

    _instance = None

    def __new__(cls):
        """Вернуть единственный экземпляр загрузчика"""
        # __new__ управляет созданием объекта и позволяет явно
        # вернуть сохранённый экземпляр при повторном вызове конструктора.
        # Такой способ проще и нагляднее метакласса Singleton.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Прочитать конфигурацию только при первом успешном создании"""
        if self._initialized:
            return
        self.reload()
        self._initialized = True

    def get(self, key: str, default: Any = None) -> Any:
        """Вернуть настройку или default; пути возвращаются как Path"""
        return self._settings.get(key, default)

    def reload(self) -> None:
        """Перезагрузить настройки; при ошибке сохранить прежний кеш"""
        try:
            with CONFIG_FILE.open("rb") as file:
                document = tomllib.load(file)
        except OSError as error:
            raise OSError(f"Не удалось прочитать настройки: {CONFIG_FILE}") from error
        except tomllib.TOMLDecodeError as error:
            raise ValueError("Некорректный TOML в файле настроек") from error

        settings = document.get("tool", {}).get("valutatrade")
        if not isinstance(settings, dict):
            raise ValueError("В pyproject.toml отсутствует секция [tool.valutatrade]")
        settings = settings.copy()

        for key in PATH_SETTINGS:
            value = settings.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Настройка '{key}' должна содержать непустой путь")
            # Относительные пути отсчитываются от проекта
            settings[key] = (PROJECT_ROOT / value).resolve()

        for key in POSITIVE_INTEGER_SETTINGS:
            value = settings.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"Настройка '{key}' должна быть положительным целым")

        balance = settings.get("initial_usd_balance")
        if isinstance(balance, bool) or not isinstance(balance, (int, float)):
            raise ValueError("Начальный баланс USD должен быть числом")
        if not math.isfinite(balance) or balance < 0:
            raise ValueError(
                "Начальный баланс USD должен быть конечным и неотрицательным"
            )

        settings.setdefault("actions_log_filename", DEFAULT_ACTIONS_LOG_FILENAME)
        settings.setdefault("log_date_format", DEFAULT_LOG_DATE_FORMAT)
        for key in (
            "default_base_currency",
            "log_format",
            "log_date_format",
            "log_level",
            "actions_log_filename",
        ):
            value = settings.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Настройка '{key}' должна быть непустой строкой")

        filename = settings["actions_log_filename"]
        if Path(filename).name != filename:
            raise ValueError("В actions_log_filename укажите имя файла без каталога")

        settings["log_level"] = settings["log_level"].upper()
        if settings["log_level"] not in ALLOWED_LOG_LEVELS:
            raise ValueError("Уровень логирования должен быть INFO или DEBUG")

        # Проверяем форматы на пробной записи без создания файлов и логгеров.
        try:
            formatter = logging.Formatter(
                fmt=settings["log_format"], datefmt=settings["log_date_format"]
            )
            formatter.converter = time.gmtime
            record = logging.LogRecord("config", logging.INFO, "", 0, "check", (), None)
            formatter.format(record)
            formatter.formatTime(record, settings["log_date_format"])
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError("Некорректный log_format или log_date_format") from error

        backups = settings.get("log_backup_count")
        if isinstance(backups, bool) or not isinstance(backups, int) or backups < 0:
            raise ValueError("Число архивных логов должно быть неотрицательным целым")

        self._settings = settings
