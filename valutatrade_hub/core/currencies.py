"""Иерархия и реестр валют"""

import math
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError

MIN_CODE_LENGTH = 2
MAX_CODE_LENGTH = 5
MARKET_CAP_PRECISION = 2


class Currency(ABC):
    """Базовый класс валюты"""

    _code: str
    _name: str

    def __init__(self, code: str, name: str) -> None:
        """Создать валюту с проверкой кода и названия."""
        self.code = code
        self.name = name

    @property
    def code(self) -> str:
        """Вернуть код валюты"""
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        """Установить код валюты верхний регистр, 2-5 символов, без пробелов"""
        if not isinstance(value, str):
            raise TypeError("Код валюты должен быть строкой")
        code = value.strip().upper()
        if not (MIN_CODE_LENGTH <= len(code) <= MAX_CODE_LENGTH):
            raise ValueError(
                f"Код валюты должен содержать от {MIN_CODE_LENGTH} "
                f"до {MAX_CODE_LENGTH} символов"
            )
        if any(char.isspace() for char in code):
            raise ValueError("Код валюты не должен содержать пробелов")
        self._code = code

    @property
    def name(self) -> str:
        """Вернуть название валюты"""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Установить название валюты"""
        if not isinstance(value, str):
            raise TypeError("Название валюты должно быть строкой")
        if not value.strip():
            raise ValueError("Название валюты не может быть пустым")
        self._name = value.strip()

    @abstractmethod
    def get_display_info(self) -> str:
        """Вернуть строковое представление для UI/логов"""
        pass


class FiatCurrency(Currency):
    """Класс для фиатных валют"""

    _issuing_country: str

    def __init__(self, code: str, name: str, issuing_country: str) -> None:
        """Создать фиатную валюту со страной или зоной эмиссии."""
        super().__init__(code, name)
        self.issuing_country = issuing_country

    @property
    def issuing_country(self) -> str:
        """Вернуть страну-эмитента валюты"""
        return self._issuing_country

    @issuing_country.setter
    def issuing_country(self, value: str) -> None:
        """Установить страну-эмитента валюты"""
        if not isinstance(value, str):
            raise TypeError("Страна-эмитент должна быть строкой")
        if not value.strip():
            raise ValueError("Страна-эмитент не может быть пустой")
        self._issuing_country = value.strip()

    def get_display_info(self) -> str:
        """Вернуть строковое представление для UI/логов"""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Класс для криптовалют"""

    _algorithm: str
    _market_cap: float

    def __init__(
        self,
        code: str,
        name: str,
        algorithm: str,
        market_cap: float,
    ) -> None:
        """Создать криптовалюту с алгоритмом и известной капитализацией."""
        super().__init__(code, name)
        self.algorithm = algorithm
        self.market_cap = market_cap

    @property
    def algorithm(self) -> str:
        """Вернуть алгоритм хэширования"""
        return self._algorithm

    @algorithm.setter
    def algorithm(self, value: str) -> None:
        """Установить алгоритм хэширования"""
        if not isinstance(value, str):
            raise TypeError("Алгоритм хэширования должен быть строкой")
        if not value.strip():
            raise ValueError("Алгоритм хэширования не может быть пустым")
        self._algorithm = value.strip()

    @property
    def market_cap(self) -> float:
        """Вернуть капитализацию"""
        return self._market_cap

    @market_cap.setter
    def market_cap(self, value: float) -> None:
        """Установить капитализацию"""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Капитализация должна быть числом")
        if not math.isfinite(value):
            raise ValueError("Капитализация должна быть конечным числом")
        if value < 0:
            raise ValueError("Капитализация не может быть отрицательной")
        self._market_cap = float(value)

    def get_display_info(self) -> str:
        """Вернуть строковое представление для UI/логов"""
        # 1.12e+12 преобразуем в краткую запись 1.12e12
        mantissa, exponent = f"{self.market_cap:.{MARKET_CAP_PRECISION}e}".split("e")
        market_cap = f"{mantissa}e{int(exponent)}"
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {market_cap})"
        )


# Нулевые капитализации — заглушки, а не рыночная статистика.
CURRENCY_REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency("USD", "US Dollar", "United States"),
    "EUR": FiatCurrency("EUR", "Euro", "Eurozone"),
    "RUB": FiatCurrency("RUB", "Russian Ruble", "Russia"),
    "BTC": CryptoCurrency("BTC", "Bitcoin", "SHA-256", 0.0),
    "ETH": CryptoCurrency("ETH", "Ethereum", "Ethash", 0.0),
}


def get_currency(code: str) -> Currency:
    """Вернуть валюту из реестра или выбросить CurrencyNotFoundError."""
    if not isinstance(code, str):
        raise TypeError("Код валюты должен быть строкой")
    if not code.strip():
        raise ValueError("Код валюты не может быть пустым")

    normalized_code = code.strip().upper()
    if normalized_code not in CURRENCY_REGISTRY:
        raise CurrencyNotFoundError(normalized_code)

    return CURRENCY_REGISTRY[normalized_code]
