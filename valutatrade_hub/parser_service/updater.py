"""Обновление курсов с сохранением данных при частичном сбое источников"""

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import validate_rate
from valutatrade_hub.logging_config import get_parser_logger
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import (
    COINGECKO_SOURCE,
    EXCHANGERATE_SOURCE,
    SOURCES,
    ParserConfig,
)
from valutatrade_hub.parser_service.storage import RatesStorage


class RatesUpdater:
    """Последовательно опросить переданные клиенты и сохранить измерения"""

    def __init__(self, clients: list[BaseApiClient], storage: RatesStorage) -> None:
        """Принять готовые клиенты и хранилище для независимой проверки."""
        self.clients = clients
        self.storage = storage

    def run_update(self) -> dict:
        """Вернуть число обновлений, время и ошибки,
        при полном сбое бросить исключение"""
        logger = get_parser_logger()
        logger.info("Начато обновление курсов")
        measurements = []
        errors = []
        previous = self.storage.read_rates()["pairs"]
        for client in self.clients:
            try:
                logger.info("Получение курсов из %s", client.name)
                rates = client.fetch_rates()
                if not isinstance(rates, dict) or not rates:
                    raise ApiRequestError(f"{client.name}: источник не вернул курсы")
                # Проверяем весь ответ до добавления измерений
                for pair, rate in rates.items():
                    try:
                        validate_rate(rate, pair)
                    except (TypeError, ValueError) as error:
                        raise ApiRequestError(f"{client.name}: {error}") from None
                for pair, rate in rates.items():
                    meta = client.meta.copy()
                    if client.name == CoinGeckoClient.name:
                        meta["raw_id"] = client.config.CRYPTO_ID_MAP[pair.split("_")[0]]
                    measurements.append(
                        {
                            "pair": pair,
                            "rate": rate,
                            "updated_at": client.updated_at,
                            "source": client.name,
                            "meta": meta,
                        }
                    )
                    logger.debug(
                        "%s: было %s, стало %s; метаданные %s",
                        pair,
                        previous.get(pair, {}).get("rate"),
                        rate,
                        meta,
                    )
                logger.info("%s: получено курсов: %s", client.name, len(rates))
            except ApiRequestError as error:
                errors.append(str(error))
                logger.error("%s", error)
                logger.debug("Подробности ошибки источника", exc_info=True)
        if not measurements:
            logger.error("Обновление завершено без данных")
            raise ApiRequestError(
                "Все выбранные источники недоступны. " + "; ".join(errors)
            )
        logger.info("Сохранение %s измерений", len(measurements))
        result = self.storage.save(measurements)
        result["errors"] = errors
        logger.info(
            "Обновление завершено: обновлено %s курсов", result["updated_count"]
        )
        return result


def create_updater(source: str | None = None) -> RatesUpdater:
    """Собрать парсер для всех источников либо одного указанного"""
    if source is not None and source not in SOURCES:
        raise ValueError("Источник должен быть coingecko или exchangerate")
    config = ParserConfig()
    clients = []
    if source is None or source == COINGECKO_SOURCE:
        clients.append(CoinGeckoClient(config))
    if source is None or source == EXCHANGERATE_SOURCE:
        clients.append(ExchangeRateApiClient(config))
    return RatesUpdater(clients, RatesStorage(config))
