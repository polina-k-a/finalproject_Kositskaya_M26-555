"""Единый доступ к JSON-хранилищу приложения."""

from collections.abc import Callable

from valutatrade_hub.core.utils import load_json, save_json
from valutatrade_hub.infra.settings import (
    PORTFOLIOS_FILE_KEY,
    RATES_FILE_KEY,
    USERS_FILE_KEY,
    SettingsLoader,
)

USERS_STORAGE = "users"
PORTFOLIOS_STORAGE = "portfolios"
RATES_STORAGE = "rates"

STORAGE_SETTINGS = {
    USERS_STORAGE: USERS_FILE_KEY,
    PORTFOLIOS_STORAGE: PORTFOLIOS_FILE_KEY,
    RATES_STORAGE: RATES_FILE_KEY,
}


class DatabaseManager:
    """Синглтон чтения, записи и изменения JSON в одном процессе"""

    _instance = None

    def __new__(cls):
        """Вернуть единственный экземпляр менеджера"""
        # __new__ управляет созданием объекта и позволяет явно
        # вернуть сохранённый экземпляр при повторном вызове конструктора.
        # Такой способ проще и нагляднее метакласса Singleton.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Один раз подключить настройки."""
        if self._initialized:
            return
        self._settings = SettingsLoader()
        self._initialized = True

    def read(self, storage: str) -> list | dict:
        """Прочитать users, portfolios или rates по настроенному пути"""
        key = self._get_setting_key(storage)
        try:
            data = load_json(self._settings.get(key))
        except FileNotFoundError:
            # При первом запуске установленного пакета файлов ещё нет.
            if storage in (USERS_STORAGE, PORTFOLIOS_STORAGE):
                data = []
            else:
                raise
        return data

    def write(self, storage: str, data: list | dict) -> None:
        """Атомарно заменить содержимое одного JSON-файла."""
        key = self._get_setting_key(storage)
        save_json(self._settings.get(key), data)

    def update(
        self,
        storage: str,
        transform: Callable[[list | dict], list | dict],
    ) -> list | dict:
        """Последовательно прочитать, преобразовать и сохранить один файл."""
        # Если transform выбрасывает исключение, запись не выполняется
        data = self.read(storage)
        updated = transform(data)
        self.write(storage, updated)
        return updated

    @staticmethod
    def _get_setting_key(storage: str) -> str:
        """Получить ключ пути для известного имени хранилища."""
        if storage not in STORAGE_SETTINGS:
            raise ValueError(f"Неизвестное хранилище '{storage}'")
        return STORAGE_SETTINGS[storage]
