"""Модели пользователя, валютного кошелька и портфеля."""

import hashlib
import math
import os
from datetime import datetime, timezone

from valutatrade_hub.core.utils import format_balance

PASSWORD_HASH_ITERATIONS = 100_000
EXCHANGE_RATES = {
    "USD_USD": 1.0,
    "EUR_USD": 1.08,
    "RUB_USD": 0.01,
    "BTC_USD": 60_000.0,
    "ETH_USD": 3_000.0,
}
PASSWORD_SALT_BYTES = 16
BALANCE_ABS_TOLERANCE = 1e-12


class User:
    """Пользователь с хешированием пароля через PBKDF2-HMAC-SHA256."""

    _user_id: int
    _username: str
    _hashed_password: str
    _salt: str
    _registration_date: datetime

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ) -> None:
        """Создать пользователя из переданных данных."""
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise TypeError("ID пользователя должен быть целым числом")
        if user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным")

        if not isinstance(hashed_password, str):
            raise TypeError("Хеш пароля должен быть строкой")
        if not hashed_password.strip():
            raise ValueError("Хеш пароля не может быть пустым")

        if not isinstance(salt, str):
            raise TypeError("Соль должна быть строкой")
        if not salt.strip():
            raise ValueError("Соль не может быть пустой")

        if not isinstance(registration_date, datetime):
            raise TypeError("Дата регистрации пользователя должна быть datetime")

        self.username = username
        self._user_id = user_id
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> "User":
        """Создать нового пользователя с исходным паролем."""
        salt, hashed_password = cls.create_password_hash(password)

        return cls(
            user_id=user_id,
            username=username,
            hashed_password=hashed_password,
            salt=salt,
            registration_date=datetime.now(timezone.utc),
        )

    @property
    def user_id(self) -> int:
        """Вернуть id пользователя"""
        return self._user_id

    @property
    def username(self) -> str:
        """Вернуть имя пользователя"""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        """Установить непустое имя пользователя"""
        if not isinstance(value, str):
            raise TypeError("Имя пользователя должно быть строкой")
        if not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value

    @property
    def registration_date(self) -> datetime:
        """Вернуть дату регистрации"""
        return self._registration_date

    @property
    def hashed_password(self) -> str:
        """Вернуть хеш пароля"""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Вернуть соль"""
        return self._salt

    def get_user_info(self) -> None:
        """Вывести информацию о пользователе без хеша пароля и соли."""
        print(f"ID пользователя: {self.user_id}")
        print(f"Имя пользователя: {self.username}")
        print(f"Дата регистрации: {self.registration_date.isoformat()}")

    def change_password(self, new_password: str) -> None:
        """Изменяет пароль пользователя,
        с хешированием нового пароля через PBKDF2-HMAC-SHA256"""
        if not isinstance(new_password, str):
            raise TypeError("Пароль должен быть строкой")
        if len(new_password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")
        self._hashed_password = hashlib.pbkdf2_hmac(
            "sha256",
            new_password.encode(),
            self._salt.encode(),
            PASSWORD_HASH_ITERATIONS,
        ).hex()

    def verify_password(self, password: str) -> bool:
        """Проверяет введённый пароль на совпадение"""
        if not isinstance(password, str):
            raise TypeError("Пароль должен быть строкой")
        hashed = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), self._salt.encode(), PASSWORD_HASH_ITERATIONS
        ).hex()
        return hashed == self._hashed_password

    @staticmethod
    def create_password_hash(password: str) -> tuple[str, str]:
        """Проверить новый пароль и вернуть соль и PBKDF2-HMAC-SHA256 хеш."""
        if not isinstance(password, str):
            raise TypeError("Пароль должен быть строкой")
        if len(password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")

        salt = os.urandom(PASSWORD_SALT_BYTES).hex()
        hashed_password = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt.encode(),
            PASSWORD_HASH_ITERATIONS,
        ).hex()

        return salt, hashed_password


class Wallet:
    """Кошелёк пользователя для одной валюты"""

    currency_code: str
    _balance: float

    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        """Создать кошелёк с указанной валютой и балансом."""
        if not isinstance(currency_code, str):
            raise TypeError("Код валюты должен быть строкой")
        if not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")

        self.currency_code = currency_code.strip().upper()
        self.balance = balance

    @property
    def balance(self) -> float:
        """Вернуть текущий баланс."""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        """Установить конечный неотрицательный баланс."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if not math.isfinite(value):
            raise ValueError("Баланс должен быть конечным числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """Пополнить кошелёк на указанную сумму."""
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError("Сумма для пополнения баланса должна быть числом")
        if amount <= 0 or not math.isfinite(amount):
            raise ValueError(
                "Сумма для пополнения баланса должна быть положительным конечным числом"
            )
        new_balance = self._balance + amount
        if not math.isfinite(new_balance):
            raise ValueError("Слишком большая сумма пополнения")
        self._balance = new_balance

    def withdraw(self, amount: float) -> None:
        """Снять сумму, учитывая абсолютную погрешность полного снятия."""
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError("Сумма для снятия с баланса должна быть числом")
        if amount <= 0 or not math.isfinite(amount):
            raise ValueError(
                "Сумма для снятия с баланса должна быть положительным конечным числом"
            )
        # float может дать 0.19999999999999998 вместо 0.2.
        if self._balance > 0 and math.isclose(
            amount,
            self._balance,
            rel_tol=0.0,
            abs_tol=BALANCE_ABS_TOLERANCE,
        ):
            self._balance = 0.0
            return

        if amount > self._balance:
            raise ValueError(
                f"Недостаточно средств: доступно "
                f"{format_balance(self.balance, self.currency_code)} "
                f"{self.currency_code}, требуется "
                f"{format_balance(amount, self.currency_code)} {self.currency_code}"
            )
        self._balance -= amount

    def get_balance_info(self) -> None:
        """Вывести текущий баланс кошелька."""
        print(f"{self.currency_code}: {self.balance}")


class Portfolio:
    """Портфель валютных кошельков одного пользователя"""

    _user_id: int
    _wallets: dict[str, Wallet]
    _user: User | None

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ) -> None:
        """Создать портфель пользователя"""
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise TypeError("ID пользователя должен быть целым числом")
        if user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным")

        if user is not None:
            if not isinstance(user, User):
                raise TypeError("Пользователь должен быть объектом User")
            if user.user_id != user_id:
                raise ValueError("ID пользователя не совпадает с владельцем портфеля")

        if wallets is None:
            wallets = {}
        if not isinstance(wallets, dict):
            raise TypeError("Кошельки должны быть словарём")

        for code, wallet in wallets.items():
            if not isinstance(wallet, Wallet):
                raise TypeError("Значения словаря должны быть объектами Wallet")
            if code != wallet.currency_code:
                raise ValueError("Ключ словаря должен совпадать с кодом кошелька")

        self._user_id = user_id
        self._wallets = wallets.copy()
        self._user = user

    @property
    def user_id(self) -> int:
        """Вернуть ID владельца портфеля"""
        return self._user_id

    @property
    def user(self) -> User | None:
        """Вернуть переданный объект пользователя"""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Вернуть копию словаря кошельков"""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> None:
        """Добавить новый кошелёк в портфель"""
        if not isinstance(currency_code, str):
            raise TypeError("Код валюты должен быть строкой")
        if not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")

        code = currency_code.strip().upper()

        if code in self._wallets:
            raise ValueError(f"Кошелёк '{code}' уже существует")

        self._wallets[code] = Wallet(code)

    def get_total_value(
        self,
        base_currency: str = "USD",
        rates: dict[str, float] | None = None,
    ) -> float:
        """Рассчитать общую стоимость всех валют пользователя
        в базовой валюте через USD."""
        if not isinstance(base_currency, str):
            raise TypeError("Код базовой валюты должен быть строкой")
        if not base_currency.strip():
            raise ValueError("Код базовой валюты не может быть пустым")

        base = base_currency.strip().upper()

        if rates is None:
            rates = EXCHANGE_RATES
        if not isinstance(rates, dict):
            raise TypeError("Курсы должны быть словарём")

        def rate_to_usd(code: str) -> float:
            """Получить курс валюты к USD."""
            if code == "USD":
                return 1.0

            pair = f"{code}_USD"
            if pair not in rates:
                raise ValueError(f"Не удалось получить курс для {code} -> USD")

            rate = rates[pair]
            if isinstance(rate, bool) or not isinstance(rate, (int, float)):
                raise TypeError(f"Курс {pair} в словаре обмена должен быть числом")
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError(
                    f"Курс {pair} в словаре обмена должен быть положительным "
                    "конечным числом"
                )

            return float(rate)

        base_rate = rate_to_usd(base)
        total = 0.0

        for code, wallet in self._wallets.items():
            if code == base:
                total += wallet.balance
            else:
                currency_rate = rate_to_usd(code)
                total += wallet.balance * currency_rate / base_rate

        return total

    def get_wallet(self, currency_code: str) -> Wallet:
        """Вернуть кошелёк по коду валюты"""
        if not isinstance(currency_code, str):
            raise TypeError("Код валюты должен быть строкой")
        if not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")

        code = currency_code.strip().upper()
        if code not in self._wallets:
            raise ValueError(
                f"У вас нет кошелька '{code}'. Добавьте валюту: "
                "она создаётся автоматически при первой покупке."
            )

        return self._wallets[code]
