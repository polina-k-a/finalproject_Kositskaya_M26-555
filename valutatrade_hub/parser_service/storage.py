"""История измерений и последний снимок курсов"""

from datetime import datetime, timezone

from valutatrade_hub.core.currencies import MAX_CODE_LENGTH, MIN_CODE_LENGTH
from valutatrade_hub.core.utils import (
    create_json_cache,
    load_json,
    parse_utc_timestamp,
    save_json,
    validate_rate,
)
from valutatrade_hub.parser_service.config import BASE_CURRENCY, ParserConfig


class RatesStorage:
    """Чтение кеша и сохранение истории без повторных ID"""

    def __init__(self, config: ParserConfig) -> None:
        """Сохранить пути и создать собственный кеш чтения через замыкание"""
        self.config = config
        self._read_cache = create_json_cache()

    def read_rates(self) -> dict:
        """Прочитать снимок или вернуть пустые пары при отсутствии файла"""
        try:
            cache = self._read_cache(self.config.RATES_FILE_PATH)
        except FileNotFoundError:
            return {"pairs": {}, "last_refresh": None}
        if not isinstance(cache, dict):
            raise ValueError("Файл курсов должен содержать объект JSON")
        # Поддерживаем кеш старого формата без поля pairs
        if "pairs" not in cache:
            cache = self._convert_old_cache(cache)
        if not isinstance(cache["pairs"], dict):
            raise ValueError("Поле pairs должно содержать объект JSON")
        cache.setdefault("last_refresh", None)
        if cache["last_refresh"] is not None:
            parse_utc_timestamp(cache["last_refresh"])
        for pair, record in cache["pairs"].items():
            self._validate_record(pair, record)
        return cache

    @staticmethod
    def _validate_record(pair: str, record: dict) -> None:
        """Проверить пару X_USD, курс, время и источник перед сохранением"""
        if not isinstance(pair, str) or pair.count("_") != 1:
            raise ValueError("Пара валют должна иметь вид X_USD")
        if not pair.endswith(f"_{BASE_CURRENCY}"):
            raise ValueError("В кеше должны храниться пары к USD")
        for code in pair.split("_"):
            if not MIN_CODE_LENGTH <= len(code) <= MAX_CODE_LENGTH:
                raise ValueError(f"Некорректная длина кода валюты в паре {pair}")
            if code != code.upper():
                raise ValueError(f"Некорректный код валюты в паре {pair}")
            if any(char.isspace() for char in code):
                raise ValueError(f"Пробел в коде валюты пары {pair}")
        if not isinstance(record, dict):
            raise ValueError(f"Некорректная запись курса {pair}")
        validate_rate(record.get("rate"), pair)
        parse_utc_timestamp(record.get("updated_at"))
        if not isinstance(record.get("source"), str) or not record["source"].strip():
            raise ValueError(f"Не указан источник курса {pair}")

    def save(self, measurements: list[dict]) -> dict:
        """Добавить измерения в историю и обновить только более свежие пары"""
        cache = self.read_rates()
        history = self._read_history()
        existing_ids = {record["id"] for record in history}
        updated_count = 0

        for measurement in measurements:
            record = self._make_history_record(measurement)

            # В истории сохраняем каждое измерение только один раз
            if record["id"] not in existing_ids:
                history.append(record)
                existing_ids.add(record["id"])

            # В снимке оставляем только самое свежее измерение каждой пары
            if self._update_pair(cache["pairs"], record):
                updated_count += 1

        if updated_count:
            cache["last_refresh"] = datetime.now(timezone.utc).isoformat()

        save_json(self.config.HISTORY_FILE_PATH, history)
        save_json(self.config.RATES_FILE_PATH, cache)
        return {"updated_count": updated_count, "last_refresh": cache["last_refresh"]}

    def _read_history(self) -> list[dict]:
        """Прочитать историю; при отсутствии файла вернуть пустой список"""
        try:
            history = load_json(self.config.HISTORY_FILE_PATH)
        except FileNotFoundError:
            history = []
        if not isinstance(history, list):
            raise ValueError("История курсов должна содержать список")
        if any(not isinstance(row, dict) or "id" not in row for row in history):
            raise ValueError("Некорректная запись истории курсов")
        return history

    def _make_history_record(self, measurement: dict) -> dict:
        """Проверить измерение и оформить одну запись для истории"""
        pair = measurement["pair"]
        self._validate_record(pair, measurement)
        timestamp = parse_utc_timestamp(measurement["updated_at"]).isoformat()
        from_code, to_code = pair.split("_")
        return {
            "id": f"{pair}_{timestamp}",
            "from_currency": from_code,
            "to_currency": to_code,
            "rate": measurement["rate"],
            "timestamp": timestamp,
            "source": measurement["source"],
            "meta": measurement.get("meta", {}),
        }

    @staticmethod
    def _update_pair(pairs: dict, record: dict) -> bool:
        """Обновить пару более свежим измерением
        Возвращает, было ли обновление"""
        pair = f"{record['from_currency']}_{record['to_currency']}"
        previous = pairs.get(pair)
        if previous is not None:
            new_time = parse_utc_timestamp(record["timestamp"])
            previous_time = parse_utc_timestamp(previous["updated_at"])
            if new_time <= previous_time:
                return False

        pairs[pair] = {
            "rate": record["rate"],
            "updated_at": record["timestamp"],
            "source": record["source"],
        }
        return True

    @staticmethod
    def _convert_old_cache(cache: dict) -> dict:
        """Преобразовать старый плоский формат в объект с полем pairs"""
        pairs = {}
        for pair, record in cache.items():
            if pair in ("source", "last_refresh"):
                continue
            if not isinstance(record, dict):
                raise ValueError(f"Некорректная запись курса {pair}")
            pairs[pair] = record.copy()
            pairs[pair].setdefault("source", cache.get("source", "Legacy"))
        return {"pairs": pairs, "last_refresh": cache.get("last_refresh")}
