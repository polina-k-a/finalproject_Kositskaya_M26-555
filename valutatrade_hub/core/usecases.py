"""Бизнес-логика регистрации, входа и операций с валютами."""

import math
from datetime import datetime, timezone

from valutatrade_hub.core.currencies import CryptoCurrency, get_currency
from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import parse_utc_timestamp, validate_rate
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import (
    PORTFOLIOS_STORAGE,
    USERS_STORAGE,
    DatabaseManager,
)
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.config import (
    COINGECKO_SOURCE,
    EXCHANGERATE_SOURCE,
    ParserConfig,
)
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import create_updater


def register(
    username: str,
    password: str,
    initial_balance: float | None = None,
) -> User:
    """Зарегистрировать пользователя с начальным виртуальным балансом USD."""
    # None означает отсутствие аргумента; явный нулевой баланс допустим.
    if initial_balance is None:
        initial_balance = SettingsLoader().get("initial_usd_balance")
    # Проверяем начальный баланс правилами Wallet до изменения хранилища.
    usd_wallet = Wallet("USD", balance=initial_balance)
    database = DatabaseManager()
    users = database.read(USERS_STORAGE)
    if not isinstance(users, list):
        raise ValueError("Файл пользователей должен содержать список")
    portfolios = database.read(PORTFOLIOS_STORAGE)
    if not isinstance(portfolios, list):
        raise ValueError("Файл портфелей должен содержать список")

    if any(u["username"] == username for u in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")
    new_id = max((record["user_id"] for record in users), default=0) + 1
    if any(portfolio["user_id"] == new_id for portfolio in portfolios):
        raise ValueError(
            f"Нарушена целостность данных: портфель для ID {new_id} уже существует"
        )

    new_user = User.create(
        user_id=new_id,
        username=username,
        password=password,
    )
    users.append(
        {
            "user_id": new_user.user_id,
            "username": new_user.username,
            "hashed_password": new_user.hashed_password,
            "salt": new_user.salt,
            "registration_date": new_user.registration_date.isoformat(),
        }
    )
    portfolios.append(
        {
            "user_id": new_user.user_id,
            "wallets": {
                "USD": {"balance": usd_wallet.balance},
            },
        }
    )

    database.write(USERS_STORAGE, users)
    try:
        database.write(PORTFOLIOS_STORAGE, portfolios)
    except OSError as error:
        # Если портфель не сохранился, отменяем добавление пользователя.
        # DatabaseManager сохраняет прежний файл при неудачной записи.
        try:
            database.write(USERS_STORAGE, users[:-1])
        except OSError as rollback_error:
            raise OSError(
                "Не удалось сохранить портфель и отменить регистрацию. "
                f"Ошибка сохранения портфеля: {error}"
            ) from rollback_error
        raise OSError("Регистрация отменена: не удалось сохранить портфель") from error

    return new_user


def login(username: str, password: str) -> User:
    """Проверить данные входа и вернуть пользователя."""
    database = DatabaseManager()
    if not isinstance(username, str):
        raise TypeError("Имя пользователя должно быть строкой")
    if not username.strip():
        raise ValueError("Имя пользователя должно быть не пустой строкой")
    if not isinstance(password, str):
        raise TypeError("Пароль должен быть строкой")
    users = database.read(USERS_STORAGE)
    if not isinstance(users, list):
        raise ValueError("Файл пользователей должен содержать список")

    for u in users:
        if u["username"] == username:
            user_data = u.copy()
            user_data["registration_date"] = datetime.fromisoformat(
                user_data["registration_date"]
            )
            user = User(**user_data)

            if not user.verify_password(password):
                raise ValueError("Неверный пароль")

            return user
    raise ValueError(f"Пользователь '{username}' не найден")


def get_rate(from_code: str, to_code: str) -> tuple[float, str]:
    """Вернуть свежий курс; при устаревшем кеше обновить нужные источники."""
    from_code = get_currency(from_code).code
    to_code = get_currency(to_code).code
    now = datetime.now(timezone.utc)
    if from_code == to_code:
        return 1.0, now.isoformat()

    storage = RatesStorage(ParserConfig())
    cache = storage.read_rates()
    from_data = _read_cached_rate(from_code, cache["pairs"], now)
    to_data = _read_cached_rate(to_code, cache["pairs"], now)
    if from_data is None or to_data is None:
        sources = set()
        for code, data in ((from_code, from_data), (to_code, to_data)):
            if data is None:
                source = (
                    COINGECKO_SOURCE
                    if isinstance(get_currency(code), CryptoCurrency)
                    else EXCHANGERATE_SOURCE
                )
                sources.add(source)
        # Один источник обновляем отдельно, два — одним общим запуском.
        source = sources.pop() if len(sources) == 1 else None
        create_updater(source).run_update()
        now = datetime.now(timezone.utc)
        cache = storage.read_rates()
        from_data = _read_cached_rate(from_code, cache["pairs"], now)
        to_data = _read_cached_rate(to_code, cache["pairs"], now)
        if from_data is None or to_data is None:
            raise ApiRequestError(
                f"Свежий курс {from_code}→{to_code} недоступен. "
                "Повторите позже или выполните update-rates."
            )

    from_rate, from_updated_at = from_data
    to_rate, to_updated_at = to_data
    try:
        rate = validate_rate(from_rate / to_rate, f"{from_code}_{to_code}")
    except (TypeError, ValueError) as error:
        raise ApiRequestError(str(error)) from error
    return rate, min(from_updated_at, to_updated_at).isoformat()


def _read_cached_rate(
    code: str,
    pairs: dict,
    now: datetime,
) -> tuple[float, datetime] | None:
    """Вернуть свежий курс к USD или None, если требуется обновление."""
    if code == "USD":
        return 1.0, now
    pair = f"{code}_USD"
    record = pairs.get(pair)
    if record is None:
        return None
    rate = validate_rate(record["rate"], pair)
    updated_at = parse_utc_timestamp(record["updated_at"])
    age = (now - updated_at).total_seconds()
    if age < 0 or age >= SettingsLoader().get("rates_ttl_seconds"):
        return None
    return rate, updated_at


def update_rates(source: str | None = None) -> dict:
    """Вручную обновить курсы выбранных источников."""
    return create_updater(source).run_update()


def show_rates(
    currency_code: str | None = None,
    top: int | None = None,
    base_currency: str = "USD",
) -> dict:
    """Подготовить курсы из кеша без сетевых запросов и скрытия их возраста."""
    base = get_currency(base_currency).code
    if top is not None:
        if isinstance(top, bool) or not isinstance(top, int) or top <= 0:
            raise ValueError("Аргумент --top должен быть положительным целым числом")
    cache = RatesStorage(ParserConfig()).read_rates()
    pairs = cache["pairs"]
    if not pairs:
        raise ValueError(
            "Локальный кеш курсов пуст. Выполните 'update-rates', "
            "чтобы загрузить данные."
        )
    if currency_code is not None:
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты должен быть непустой строкой")
        currency_code = currency_code.strip().upper()
        if currency_code != "USD" and f"{currency_code}_USD" not in pairs:
            raise ValueError(f"Курс для '{currency_code}' не найден в кеше.")
        get_currency(currency_code)
    if base != "USD" and f"{base}_USD" not in pairs:
        raise ValueError(f"Курс для '{base}' не найден в кеше.")
    base_rate = 1.0 if base == "USD" else pairs[f"{base}_USD"]["rate"]
    rows = []
    now = datetime.now(timezone.utc)
    codes = [pair.split("_")[0] for pair in pairs]
    if currency_code == "USD":
        codes = ["USD"]
    for code in codes:
        if currency_code is not None and code != currency_code:
            continue
        if top is not None and not isinstance(get_currency(code), CryptoCurrency):
            continue
        record = pairs.get(f"{code}_USD")
        rate = 1.0 if code == "USD" else record["rate"]
        times = []
        if record is not None:
            times.append(parse_utc_timestamp(record["updated_at"]))
        if base != "USD":
            times.append(parse_utc_timestamp(pairs[f"{base}_USD"]["updated_at"]))
        updated_at = min(times) if times else now
        age = (now - updated_at).total_seconds()
        rows.append(
            {
                "pair": f"{code}_{base}",
                "rate": validate_rate(rate / base_rate, f"{code}_{base}"),
                "updated_at": updated_at.isoformat(),
                "stale": age < 0 or age >= SettingsLoader().get("rates_ttl_seconds"),
            }
        )
    if top is not None:
        rows.sort(key=lambda row: row["rate"], reverse=True)
        rows = rows[:top]
    else:
        rows.sort(key=lambda row: row["pair"])
    return {"rows": rows, "last_refresh": cache["last_refresh"]}


def _load_portfolio(
    user_id: int,
    user: User | None = None,
) -> tuple[list, dict, Portfolio]:
    """Загрузить портфель, вернув список записей, нужную запись и модель."""
    database = DatabaseManager()
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise TypeError("ID пользователя должен быть целым числом")
    if user_id <= 0:
        raise ValueError("ID пользователя должен быть положительным")

    portfolios = database.read(PORTFOLIOS_STORAGE)
    if not isinstance(portfolios, list):
        raise ValueError("Файл портфелей должен содержать список")

    portfolio_data = None
    for record in portfolios:
        if not isinstance(record, dict):
            raise ValueError("Запись портфеля должна быть объектом JSON")
        if record.get("user_id") == user_id:
            portfolio_data = record
            break
    if portfolio_data is None:
        raise ValueError(f"Портфель пользователя с ID {user_id} не найден")

    wallet_records = portfolio_data.get("wallets")
    if not isinstance(wallet_records, dict):
        raise ValueError("Кошельки портфеля должны быть словарём")

    # Модели создаём заново: неудачная операция не меняет данные в файле.
    wallets = {}
    for wallet_code, record in wallet_records.items():
        if not isinstance(record, dict) or "balance" not in record:
            raise ValueError(f"Некорректная запись кошелька '{wallet_code}'")
        wallet = Wallet(wallet_code, record["balance"])
        if wallet.currency_code in wallets:
            raise ValueError(f"Повторяющийся кошелёк '{wallet.currency_code}'")
        wallets[wallet.currency_code] = wallet
    portfolio = Portfolio(user_id=user_id, wallets=wallets, user=user)

    return portfolios, portfolio_data, portfolio


def show_portfolio(user_id: int, base_currency: str | None = None) -> dict:
    """Подготовить балансы и общую стоимость портфеля."""
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise TypeError("ID пользователя должен быть целым числом")
    if user_id <= 0:
        raise ValueError("ID пользователя должен быть положительным")

    if base_currency is None:
        base_currency = SettingsLoader().get("default_base_currency")
    base = get_currency(base_currency).code

    database = DatabaseManager()
    users = database.read(USERS_STORAGE)
    if not isinstance(users, list):
        raise ValueError("Файл пользователей должен содержать список")
    user = None
    for u in users:
        if u["user_id"] == user_id:
            user_data = u.copy()
            user_data["registration_date"] = datetime.fromisoformat(
                user_data["registration_date"]
            )
            user = User(**user_data)
            break
    if user is None:
        raise ValueError(f"Пользователь с ID {user_id} не найден")

    _, _, portfolio = _load_portfolio(user_id, user=user)

    # Собираем курс к USD для всех расчётов.
    base_rate, _ = get_rate(base, "USD")
    rates = {f"{base}_USD": base_rate}

    for code in portfolio.wallets:
        pair = f"{code}_USD"
        if pair not in rates:
            rates[pair], _ = get_rate(code, "USD")

    # Готовим данные строк таблицы
    wallet_rows = []
    for code, wallet in portfolio.wallets.items():
        value = wallet.balance * rates[f"{code}_USD"] / base_rate
        wallet_rows.append(
            {
                "currency_code": code,
                "balance": wallet.balance,
                "value": value,
            }
        )

    total = portfolio.get_total_value(base_currency=base, rates=rates)

    return {
        "base": base,
        "wallets": wallet_rows,
        "total": total,
    }


@log_action("BUY", verbose=True)
def buy(user_id: int, currency_code: str, amount: float) -> dict:
    """Купить валюту за USD и сохранить оба баланса в портфеле"""
    return _execute_trade(user_id, currency_code, amount, buying=True)


@log_action("SELL", verbose=True)
def sell(user_id: int, currency_code: str, amount: float) -> dict:
    """Продать валюту за USD и сохранить оба баланса в портфеле"""
    return _execute_trade(user_id, currency_code, amount, buying=False)


def _execute_trade(
    user_id: int,
    currency_code: str,
    amount: float,
    *,
    buying: bool,
) -> dict:
    """Выполнить обмен с USD; buying: True - покупка, иначе продажа"""
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise TypeError("ID пользователя должен быть целым числом")
    if user_id <= 0:
        raise ValueError("ID пользователя должен быть положительным")
    code = get_currency(currency_code).code
    if code == "USD":
        raise ValueError("Обмен USD на USD не осуществляется")

    # Проверяем вход до получения курсов и любых изменений.
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise TypeError("Сумма должна быть числом")
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("Сумма должна быть положительным конечным числом")
    amount = float(amount)

    database = DatabaseManager()
    portfolios, portfolio_data, portfolio = _load_portfolio(user_id)
    wallets = portfolio.wallets

    if not buying:
        # При продаже валютный кошелёк должен уже существовать.
        portfolio.get_wallet(code)

    rate, _ = get_rate(code, "USD")
    value = amount * rate
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Стоимость сделки должна быть положительным конечным числом")

    if buying:
        if code not in wallets:
            portfolio.add_currency(code)
        if "USD" not in wallets:
            portfolio.add_currency("USD")
    elif "USD" not in wallets:
        # Продать ранее сохранённую валюту можно и без USD-кошелька
        portfolio.add_currency("USD")

    asset_wallet = portfolio.get_wallet(code)
    usd_wallet = portfolio.get_wallet("USD")
    before = asset_wallet.balance
    usd_before = usd_wallet.balance

    if buying:
        # Проверяем новый баланс до списания долларов
        new_asset_balance = Wallet(code, asset_wallet.balance + amount)
        # withdraw проверяет достаточность средств с единой погрешностью.
        usd_wallet.withdraw(value)
        asset_wallet.balance = new_asset_balance.balance
    else:
        # Проверяем возможное переполнение USD до списания валюты
        new_usd_balance = Wallet("USD", usd_wallet.balance + value)
        asset_wallet.withdraw(amount)
        usd_wallet.balance = new_usd_balance.balance

    # Оба кошелька входят в одну запись файла
    portfolio_data["wallets"] = {
        wallet_code: {"balance": wallet.balance}
        for wallet_code, wallet in portfolio.wallets.items()
    }
    database.write(PORTFOLIOS_STORAGE, portfolios)

    return {
        "currency_code": code,
        "amount": amount,
        "rate": rate,
        "before": before,
        "after": asset_wallet.balance,
        "value": value,
        "usd_before": usd_before,
        "usd_after": usd_wallet.balance,
        "base": "USD",
    }
