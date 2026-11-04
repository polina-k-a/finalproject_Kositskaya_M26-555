"""Настройки API; ключи загружаются из окружения при создании конфигурации"""

import os
from pathlib import Path

from valutatrade_hub.core.currencies import (
    CURRENCY_REGISTRY,
    CryptoCurrency,
    FiatCurrency,
)
from valutatrade_hub.infra.settings import SettingsLoader

BASE_CURRENCY = "USD"
COINGECKO_SOURCE = "coingecko"
EXCHANGERATE_SOURCE = "exchangerate"

SOURCES = (COINGECKO_SOURCE, EXCHANGERATE_SOURCE)
CRYPTO_ID_MAP = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
FIAT_CURRENCIES = tuple(
    code
    for code, currency in CURRENCY_REGISTRY.items()
    if isinstance(currency, FiatCurrency) and code != BASE_CURRENCY
)
CRYPTO_CURRENCIES = tuple(
    code
    for code, currency in CURRENCY_REGISTRY.items()
    if isinstance(currency, CryptoCurrency)
)


class ParserConfig:
    """Параметры парсера из общих настроек и переменных окружения"""

    def __init__(self) -> None:
        """Прочитать актуальные настройки и секреты без сохранения ключей в JSON"""
        settings = SettingsLoader()

        # API-ключи из переменных окружения
        self.EXCHANGERATE_API_KEY: str = os.getenv("EXCHANGERATE_API_KEY", "").strip()
        self.COINGECKO_API_KEY: str = os.getenv("COINGECKO_API_KEY", "").strip()

        # Адреса API из общей конфигурации проекта
        self.COINGECKO_URL: str = settings.get("coingecko_url")
        self.EXCHANGERATE_API_URL: str = settings.get("exchangerate_api_url")

        # Базовая валюта, списки валют и соответствие ID в CoinGecko
        self.BASE_CURRENCY: str = BASE_CURRENCY
        self.FIAT_CURRENCIES: tuple[str, ...] = FIAT_CURRENCIES
        self.CRYPTO_CURRENCIES: tuple[str, ...] = CRYPTO_CURRENCIES
        self.CRYPTO_ID_MAP: dict[str, str] = CRYPTO_ID_MAP.copy()

        # Пути к снимку курсов и истории
        self.RATES_FILE_PATH: Path = settings.get("rates_file")
        self.HISTORY_FILE_PATH: Path = settings.get("history_file")

        # Таймаут запроса и интервал обновлений планировщика, в секундах
        self.REQUEST_TIMEOUT: int = settings.get("request_timeout")
        self.UPDATE_INTERVAL_SECONDS: int = settings.get("update_interval_seconds")
