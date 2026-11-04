"""Отдельный последовательный запуск обновлений через заданный интервал"""

import time

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import get_parser_logger
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.updater import create_updater


def main() -> None:
    """Обновлять курсы до Ctrl+C, логировать ошибки и продолжать при частичных сбоях"""
    interval = ParserConfig().UPDATE_INTERVAL_SECONDS
    updater = create_updater()
    logger = get_parser_logger()
    try:
        while True:
            try:
                updater.run_update()
            except (ApiRequestError, OSError, ValueError) as error:
                logger.error("Ошибка планировщика: %s", error)
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Планировщик остановлен")


if __name__ == "__main__":
    main()
