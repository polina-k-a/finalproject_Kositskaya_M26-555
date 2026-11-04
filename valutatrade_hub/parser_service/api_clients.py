"""API-клиенты с единым результатом: словарь пар X_USD и числовых курсов"""

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import validate_rate
from valutatrade_hub.parser_service.config import ParserConfig

HTTP_ERROR_MESSAGES = {
    401: "неверный или отсутствующий API-ключ",
    403: "доступ запрещён; проверьте ключ и тариф",
    429: "превышен лимит запросов; повторите позже",
}
MILLISECONDS_PER_SECOND = 1000


class BaseApiClient(ABC):
    """Общий интерфейс и отправка GET-запросов без раскрытия API-ключей"""

    name: str

    def __init__(self, config: ParserConfig) -> None:
        """Сохранить конфигурацию и метаданные последнего успешного запроса."""
        self.config = config
        self.updated_at = None
        self.meta = {}

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Получить курсы вида X_USD."""
        pass

    def _request_json(self, url: str, params=None, headers=None) -> dict:
        """Получить JSON, преобразовав сетевые ошибки в ApiRequestError"""
        started = time.monotonic()
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.config.REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as error:
            # Ключ содержится в URL, его не выводим
            raise ApiRequestError(
                f"{self.name}: сетевая ошибка ({type(error).__name__})"
            ) from None

        with response:
            if response.status_code != 200:
                reason = HTTP_ERROR_MESSAGES.get(
                    response.status_code, "сервис вернул ошибку"
                )
                raise ApiRequestError(
                    f"{self.name}: HTTP {response.status_code}, {reason}"
                )
            try:
                data = response.json()
            except ValueError:
                raise ApiRequestError(f"{self.name}: ответ не является JSON") from None
            if not isinstance(data, dict):
                raise ApiRequestError(f"{self.name}: ожидался объект JSON")
            self.updated_at = datetime.now(timezone.utc).isoformat()
            self.meta = {
                "request_ms": round(
                    (time.monotonic() - started) * MILLISECONDS_PER_SECOND
                ),
                "status_code": response.status_code,
                "etag": response.headers.get("ETag"),
            }
        return data


class CoinGeckoClient(BaseApiClient):
    """Получение стоимости криптовалют в USD из CoinGecko"""

    name = "CoinGecko"

    def fetch_rates(self) -> dict[str, float]:
        """Запросить выбранные ID монет и вернуть пары к USD"""
        ids = self.config.CRYPTO_ID_MAP
        params = {
            "ids": ",".join(ids[code] for code in self.config.CRYPTO_CURRENCIES),
            "vs_currencies": self.config.BASE_CURRENCY.lower(),
        }
        headers = {}
        if self.config.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = self.config.COINGECKO_API_KEY
        data = self._request_json(self.config.COINGECKO_URL, params, headers)
        rates = {}
        for code in self.config.CRYPTO_CURRENCIES:
            record = data.get(ids[code])
            if not isinstance(record, dict):
                raise ApiRequestError(f"{self.name}: отсутствуют данные {code}")
            pair = f"{code}_{self.config.BASE_CURRENCY}"
            try:
                rates[pair] = validate_rate(
                    record.get(self.config.BASE_CURRENCY.lower()), pair
                )
            except (TypeError, ValueError) as error:
                raise ApiRequestError(f"{self.name}: {error}") from None
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Получение фиатных курсов с обращением USD_X в X_USD."""

    name = "ExchangeRate-API"

    def fetch_rates(self) -> dict[str, float]:
        """Получить conversion_rates и обратить направление каждой пары."""
        if not self.config.EXCHANGERATE_API_KEY:
            raise ApiRequestError("Не задана переменная EXCHANGERATE_API_KEY")
        base = self.config.BASE_CURRENCY
        url = (
            f"{self.config.EXCHANGERATE_API_URL.rstrip('/')}"
            f"/{self.config.EXCHANGERATE_API_KEY}/latest/{base}"
        )
        data = self._request_json(url)
        if data.get("result") != "success":
            # Ответ сервера может содержать секреты - не логируем
            raise ApiRequestError(f"{self.name}: проверьте API-ключ и лимит запросов")
        if data.get("base_code") != base:
            raise ApiRequestError(f"{self.name}: неверная базовая валюта ответа")
        conversion = data.get("conversion_rates")
        if not isinstance(conversion, dict):
            raise ApiRequestError(f"{self.name}: отсутствует conversion_rates")
        rates = {}
        for code in self.config.FIAT_CURRENCIES:
            pair = f"{code}_{base}"
            try:
                direct = validate_rate(conversion.get(code), f"{base}_{code}")
                rates[pair] = validate_rate(1 / direct, pair)
            except (TypeError, ValueError) as error:
                raise ApiRequestError(f"{self.name}: {error}") from None
        return rates
