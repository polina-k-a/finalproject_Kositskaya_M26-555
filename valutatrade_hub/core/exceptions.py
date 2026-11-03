"""Пользовательские исключения приложения"""

from valutatrade_hub.core.utils import format_balance


class ValutaTradeError(Exception):
    """Базовое исключение приложения"""


class InsufficientFundsError(ValutaTradeError):
    """Недостаточно средств для выполнения операции."""

    def __init__(self, code: str, available: float, required: float) -> None:
        """Сохранить код валюты, доступный и требуемый баланс"""
        self.code = code
        self.available = available
        self.required = required
        super().__init__(
            f"Недостаточно средств: доступно {format_balance(available, code)} {code}, "
            f"требуется {format_balance(required, code)} {code}"
        )


class CurrencyNotFoundError(ValutaTradeError):
    """Валюта с указанным кодом отсутствует в реестре"""

    def __init__(self, code: str) -> None:
        """Сохранить неизвестный код и сформировать сообщение для CLI"""
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(ValutaTradeError):
    """Ошибка при обращении к внешнему API"""

    def __init__(self, reason: str) -> None:
        """Сохранить причину и сформировать сообщение для CLI"""
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
