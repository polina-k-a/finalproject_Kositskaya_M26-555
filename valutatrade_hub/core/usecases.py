"""Бизнес-логика регистрации, входа и операций с валютами."""

import math
from datetime import datetime, timezone

from valutatrade_hub.core.models import EXCHANGE_RATES, Portfolio, User, Wallet
from valutatrade_hub.core.utils import (
    PORTFOLIOS_FILE,
    RATES_FILE,
    USERS_FILE,
    load_json,
    save_json,
)

RATES_TTL_SECONDS = 300
INITIAL_USD_BALANCE = 10_000.0


def register(
    username: str,
    password: str,
    initial_balance: float = INITIAL_USD_BALANCE,
) -> User:
    """Зарегистрировать пользователя с начальным виртуальным балансом USD."""
    # Проверяем начальный баланс правилами Wallet до изменения хранилища.
    usd_wallet = Wallet("USD", balance=initial_balance)
    users = load_json(USERS_FILE)
    if not isinstance(users, list):
        raise ValueError("Файл пользователей должен содержать список")
    portfolios = load_json(PORTFOLIOS_FILE)
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

    save_json(USERS_FILE, users)
    try:
        save_json(PORTFOLIOS_FILE, portfolios)
    except OSError as error:
        # Если портфель не сохранился, отменяем добавление пользователя.
        # save_json сохраняет прежний целевой файл при неудачной записи.
        try:
            save_json(USERS_FILE, users[:-1])
        except OSError as rollback_error:
            raise OSError(
                "Не удалось сохранить портфель и отменить регистрацию. "
                f"Ошибка сохранения портфеля: {error}"
            ) from rollback_error
        raise OSError("Регистрация отменена: не удалось сохранить портфель") from error

    return new_user


def login(username: str, password: str) -> User:
    """Проверить данные входа и вернуть пользователя."""
    if not isinstance(username, str):
        raise TypeError("Имя пользователя должно быть строкой")
    if not username.strip():
        raise ValueError("Имя пользователя должно быть не пустой строкой")
    if not isinstance(password, str):
        raise TypeError("Пароль должен быть строкой")
    users = load_json(USERS_FILE)
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
    """Вернуть курс и время обновления через кеш или учебную заглушку."""
    for code in (from_code, to_code):
        if not isinstance(code, str):
            raise TypeError("Код валюты должен быть строкой")
        if not code.strip():
            raise ValueError("Код валюты не может быть пустым")

    from_code = from_code.strip().upper()
    to_code = to_code.strip().upper()

    now = datetime.now(timezone.utc)

    # курс не нужен
    if from_code == to_code:
        return 1.0, now.isoformat()

    try:
        cache = load_json(RATES_FILE)
    except FileNotFoundError:
        # Отсутствующий кеш восстановим из заглушки, остальные ошибки не перехватываем
        cache = {}

    if not isinstance(cache, dict):
        raise ValueError("Файл курсов должен содержать объект JSON")

    # Получаем стоимости единицы обеих валют в USD из кэша
    from_data = _read_cached_rate(from_code, cache, now)
    to_data = _read_cached_rate(to_code, cache, now)

    if from_data is None or to_data is None:
        for code, data in ((from_code, from_data), (to_code, to_data)):
            # Обновляем только отсутствующие или устаревшие курсы
            if data is not None:
                continue

            pair = f"{code}_USD"
            # Если в заглушке нет нужного курса, то бросаем исключение
            if pair not in EXCHANGE_RATES:
                raise ValueError(f"Не удалось получить курс для {code}→USD")

            rate = EXCHANGE_RATES[pair]

            if isinstance(rate, bool) or not isinstance(rate, (int, float)):
                raise ValueError(f"Курс {pair} в заглушке должен быть числом")
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError(
                    f"Курс {pair} в заглушке должен быть положительным конечным числом"
                )

            # Обновляем результат поиска
            rate = float(rate)
            cache[pair] = {
                "rate": rate,
                "updated_at": now.isoformat(),
            }
            if code == from_code:
                from_data = (rate, now)
            else:
                to_data = (rate, now)

        # Сохраняем после успешного получения всех недостающих курсов
        cache["source"] = "Stub"
        cache["last_refresh"] = now.isoformat()
        save_json(RATES_FILE, cache)

    from_rate, from_updated_at = from_data
    to_rate, to_updated_at = to_data

    # FROM -> USD -> TO
    rate = from_rate / to_rate
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError(
            f"Не удалось рассчитать положительный конечный курс {from_code}→{to_code}"
        )
    # Время получения курса - самый старый из двух курсов.
    updated_at = min(from_updated_at, to_updated_at)

    return rate, updated_at.isoformat()


def _read_cached_rate(
    code: str,
    cache: dict,
    now: datetime,
) -> tuple[float, datetime] | None:
    """Вернуть свежий курс к USD или None, если требуется обновление."""
    # курс не нужен
    if code == "USD":
        return 1.0, now

    pair = f"{code}_USD"
    record = cache.get(pair)

    if record is None:
        return None
    if not isinstance(record, dict):
        raise ValueError(f"Некорректная запись курса {pair}")

    rate = record.get("rate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        raise ValueError(f"Курс {pair} должен быть числом")
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError(f"Курс {pair} должен быть положительным конечным числом")

    timestamp = record.get("updated_at")
    if not isinstance(timestamp, str):
        raise ValueError(f"У курса {pair} отсутствует время обновления")

    try:
        updated_at = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise ValueError(f"Некорректное время обновления курса {pair}") from error

    # Даты без часового пояса считаем временем UTC
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    age = (now - updated_at).total_seconds()
    # Будущая дата также не подтверждает актуальность записи
    if age < 0 or age >= RATES_TTL_SECONDS:
        return None

    return float(rate), updated_at


def _load_portfolio(
    user_id: int,
    user: User | None = None,
) -> tuple[list, dict, Portfolio]:
    """Загрузить портфель, вернув список записей, нужную запись и модель."""
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise TypeError("ID пользователя должен быть целым числом")
    if user_id <= 0:
        raise ValueError("ID пользователя должен быть положительным")

    portfolios = load_json(PORTFOLIOS_FILE)
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


def show_portfolio(user_id: int, base_currency: str = "USD") -> dict:
    """Подготовить балансы и общую стоимость портфеля."""
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise TypeError("ID пользователя должен быть целым числом")
    if user_id <= 0:
        raise ValueError("ID пользователя должен быть положительным")

    if not isinstance(base_currency, str) or not base_currency.strip():
        raise ValueError("Код валюты должен быть не пустой строкой")
    base = base_currency.strip().upper()

    users = load_json(USERS_FILE)
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


def buy(user_id: int, currency_code: str, amount: float) -> dict:
    """Купить валюту за USD и сохранить оба баланса в портфеле"""
    return _execute_trade(user_id, currency_code, amount, buying=True)


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
    if not isinstance(currency_code, str):
        raise TypeError("Код валюты должен быть строкой")
    if not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым")
    code = currency_code.strip().upper()
    if code == "USD":
        raise ValueError("Обмен USD на USD не осуществляется")

    # Проверяем вход до получения курсов и любых изменений.
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise TypeError("Сумма должна быть числом")
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("Сумма должна быть положительным конечным числом")
    amount = float(amount)

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
    save_json(PORTFOLIOS_FILE, portfolios)

    return {
        "currency_code": code,
        "amount": amount,
        "rate": rate,
        "before": before,
        "after": asset_wallet.balance,
        "value": value,
        "usd_before": usd_before,
        "usd_after": usd_wallet.balance,
    }
