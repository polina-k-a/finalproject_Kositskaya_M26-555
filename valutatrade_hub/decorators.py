"""Декоратор логирования успешных и неуспешных доменных операций."""

import json
from collections.abc import Callable
from functools import wraps
from inspect import signature
from typing import Any

from valutatrade_hub.logging_config import get_action_logger

ALLOWED_ACTIONS = ("BUY", "SELL", "REGISTER", "LOGIN")
TRADE_ACTIONS = ("BUY", "SELL")
VERBOSE_RESULT_FIELDS = ("before", "after", "usd_before", "usd_after")


def _format_log_fields(fields: dict) -> str:
    """Собрать строку ключ=значение, экранируя переводы строк в значениях"""
    return " ".join(
        f"{key}={json.dumps(value, ensure_ascii=False, default=str)}"
        for key, value in fields.items()
    )


def log_action(action: str, verbose: bool = False) -> Callable:
    """Логировать действие на INFO, сохраняя результат и проброс исключений.
    Поля операции собираются здесь, ISO-время UTC добавляет форматтер логгера.
    """
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"Неизвестное действие для логирования '{action}'")
    if not isinstance(verbose, bool):
        raise TypeError("Параметр verbose должен быть bool")

    def decorate(function: Callable) -> Callable:
        """Подготовить обёртку и сохранить сигнатуру для чтения аргументов."""
        # Для логирования аргументы функции извлекаются через inspect.signature,
        function_signature = signature(function)

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Выполнить операцию и записать её результат либо исходное исключение."""
            logger = get_action_logger()
            fields = {
                "action": action,
                "user_id": None,
                "currency_code": None,
                "amount": None,
                "rate": None,
                "base": "USD" if action in TRADE_ACTIONS else None,
            }

            try:
                arguments = function_signature.bind_partial(*args, **kwargs).arguments
                for key in ("user_id", "currency_code", "amount"):
                    fields[key] = arguments.get(key)
                if "username" in arguments:
                    fields["username"] = arguments["username"]
                if isinstance(fields["currency_code"], str):
                    fields["currency_code"] = fields["currency_code"].strip().upper()

                result = function(*args, **kwargs)
            except Exception as error:
                fields.update(
                    result="ERROR",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                if verbose:
                    # При отказе результат операции отсутствует, но исключение
                    # нехватки средств содержит доступную и требуемую сумму.
                    for key in ("available", "required"):
                        if hasattr(error, key):
                            fields[key] = getattr(error, key)
                logger.info(_format_log_fields(fields))
                raise

            if isinstance(result, dict):
                for key in ("currency_code", "amount", "rate", "base"):
                    if key in result:
                        fields[key] = result[key]
                if verbose:
                    for key in VERBOSE_RESULT_FIELDS:
                        if key in result:
                            fields[key] = result[key]

            fields["result"] = "OK"
            logger.info(_format_log_fields(fields))
            return result

        return wrapper

    return decorate
