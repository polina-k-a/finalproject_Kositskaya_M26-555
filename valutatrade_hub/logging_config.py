"""Человекочитаемые логи доменных операций с ISO-временем UTC и ротацией."""

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import LOGS_DIR_KEY, SettingsLoader

ACTIONS_LOGGER_NAME = "valutatrade_hub.actions"


def get_action_logger() -> logging.Logger:
    """Настроить и вернуть логгер, не добавляя повторные обработчики"""
    settings = SettingsLoader()
    logs_dir = settings.get(LOGS_DIR_KEY)
    filename = settings.get("actions_log_filename")
    log_path = logs_dir / filename
    max_bytes = settings.get("log_max_bytes")
    backup_count = settings.get("log_backup_count")

    level = settings.get("log_level")
    formatter = _create_formatter(settings)

    logger = logging.getLogger(ACTIONS_LOGGER_NAME)
    logger.setLevel(level)
    # Записи в файл, вывод пользовательских сообщений делает CLI
    logger.propagate = False
    for handler in logger.handlers:
        # если уже есть обработчик с нужным файлом и параметрами ротации, используем его
        if (
            isinstance(handler, RotatingFileHandler)
            and handler.baseFilename == str(log_path)
            and handler.maxBytes == max_bytes
            and handler.backupCount == backup_count
        ):
            selected_handler = handler
            break
    else:
        # путь или параметры ротации изменились после settings.reload().
        selected_handler = _create_file_handler(log_path, max_bytes, backup_count)
        _remove_handlers(logger)
        logger.addHandler(selected_handler)

    selected_handler.setLevel(level)
    selected_handler.setFormatter(formatter)
    return logger


def _create_formatter(settings: SettingsLoader) -> logging.Formatter:
    """Создать форматтер с временем UTC."""
    formatter = logging.Formatter(
        fmt=settings.get("log_format"),
        datefmt=settings.get("log_date_format"),
    )
    formatter.converter = time.gmtime
    return formatter


def _create_file_handler(
    log_path: Path,
    max_bytes: int,
    backup_count: int,
) -> RotatingFileHandler:
    """Создать папку и файловый обработчик с заданными параметрами ротации."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    return handler


def _remove_handlers(logger: logging.Logger) -> None:
    """Отключить все обработчики логгера и закрыть их ресурсы."""
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
