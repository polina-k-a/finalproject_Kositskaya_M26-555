"""Ввод команд, разбор аргументов и вывод сообщений CLI."""

import shlex
from datetime import datetime, timezone

import prompt
from prettytable import PrettyTable

from valutatrade_hub.core import usecases
from valutatrade_hub.core.models import User
from valutatrade_hub.core.utils import CRYPTO_CODES, format_balance

VALUE_PRECISION = 2
RATE_PRECISION = 8
DISPLAY_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

USERNAME_OPTION = "--username"
PASSWORD_OPTION = "--password"
CURRENCY_OPTION = "--currency"
AMOUNT_OPTION = "--amount"
BASE_OPTION = "--base"
FROM_OPTION = "--from"
TO_OPTION = "--to"

REQUIRED_OPTIONS = {
    "register": (USERNAME_OPTION, PASSWORD_OPTION),
    "login": (USERNAME_OPTION, PASSWORD_OPTION),
    "show-portfolio": (),
    "buy": (CURRENCY_OPTION, AMOUNT_OPTION),
    "sell": (CURRENCY_OPTION, AMOUNT_OPTION),
    "get-rate": (FROM_OPTION, TO_OPTION),
}


def parse_options(command: str, arguments: list[str]) -> dict[str, str | float]:
    """Разобрать пары флаг-значение и проверить аргументы команды."""
    required = REQUIRED_OPTIONS[command]
    allowed = required + ((BASE_OPTION,) if command == "show-portfolio" else ())
    options = {}

    tokens = iter(arguments)
    for flag in tokens:
        if flag not in allowed:
            raise ValueError(f"Неизвестный аргумент '{flag}'")
        if flag in options:
            raise ValueError(f"Аргумент '{flag}' указан несколько раз")
        value = next(tokens, None)
        if value is None or value in allowed:
            raise ValueError(f"Не указано значение аргумента '{flag}'")

        options[flag] = value

    for flag in required:
        if flag not in options:
            raise ValueError(f"Не указан обязательный аргумент '{flag}'")

    if AMOUNT_OPTION in options:
        try:
            options[AMOUNT_OPTION] = float(options[AMOUNT_OPTION])
        except ValueError as error:
            raise ValueError(
                "Суммы для снятия и пополнения счета должны быть числами"
            ) from error

    return options


def main() -> None:
    """Запустить цикл чтения пользовательских команд."""
    print("Платформа для отслеживания и симуляции торговли валютами.")
    print("Введите help для просмотра команд, exit — для выхода.")
    current_user = None
    while True:
        line = prompt.string("> ")
        try:
            arguments = shlex.split(line)
        except ValueError as error:
            print(f"Ошибка ввода: {error}")
            continue

        if not arguments:
            continue

        command, *option_tokens = arguments

        if command in REQUIRED_OPTIONS:
            try:
                options = parse_options(command, option_tokens)
            except ValueError as error:
                print(f"Ошибка ввода: {error}")
                continue
        try:
            match command:
                case "exit":
                    if option_tokens:
                        print("Команда exit не принимает аргументы")
                        continue
                    print("Работа завершена.")
                    break
                case "help":
                    handle_help(option_tokens)
                case "register":
                    handle_register(options)
                case "login":
                    current_user = handle_login(options)
                case "show-portfolio":
                    if not current_user:
                        print("Сначала выполните login")
                        continue
                    handle_show_portfolio(options, current_user)
                case "buy":
                    if not current_user:
                        print("Сначала выполните login")
                        continue
                    handle_buy(options, current_user)
                case "sell":
                    if not current_user:
                        print("Сначала выполните login")
                        continue
                    handle_sell(options, current_user)
                case "get-rate":
                    handle_get_rate(options)
                case _:
                    print(f"Неизвестная команда '{command}'. Введите help.")
        except (TypeError, ValueError, OSError) as error:
            print(f"Ошибка: {error}")


def handle_help(arguments: list[str]) -> None:
    """Показать синтаксис всех команд."""
    if arguments:
        print("Команда help не принимает аргументы")
        return

    print(
        f"register {USERNAME_OPTION} <имя> {PASSWORD_OPTION} <пароль>\n"
        f"login {USERNAME_OPTION} <имя> {PASSWORD_OPTION} <пароль>\n"
        f"show-portfolio [{BASE_OPTION} <валюта>]\n"
        f"buy {CURRENCY_OPTION} <валюта> {AMOUNT_OPTION} <количество>\n"
        f"sell {CURRENCY_OPTION} <валюта> {AMOUNT_OPTION} <количество>\n"
        f"get-rate {FROM_OPTION} <валюта> {TO_OPTION} <валюта>\n"
        "help\n"
        "exit"
    )


def handle_register(options: dict[str, str | float]) -> None:
    """Зарегистрировать пользователя и вывести результат."""
    user = usecases.register(
        username=options[USERNAME_OPTION],
        password=options[PASSWORD_OPTION],
    )
    print(
        f"Пользователь '{user.username}' зарегистрирован "
        f"(id={user.user_id}). "
        f"Войдите: login --username {user.username} --password ****"
    )


def handle_login(options: dict[str, str | float]) -> User:
    """Проверить данные входа и вернуть пользователя для текущей сессии."""
    user = usecases.login(
        username=options[USERNAME_OPTION],
        password=options[PASSWORD_OPTION],
    )
    print(f"Вы вошли как '{user.username}'")
    return user


def handle_show_portfolio(
    options: dict[str, str | float],
    user: User,
) -> None:
    """Показать таблицу кошельков и общую сумму."""
    result = usecases.show_portfolio(
        user_id=user.user_id,
        base_currency=options.get(BASE_OPTION, "USD"),
    )

    base = result["base"]
    print(f"Портфель пользователя '{user.username}' (база: {base}):")

    if not result["wallets"]:
        print("У пользователя пока нет кошельков.")
        return

    table = PrettyTable()
    table.field_names = ["Валюта", "Баланс", f"Стоимость в {base}"]
    table.align["Валюта"] = "l"
    table.align["Баланс"] = "r"
    table.align[f"Стоимость в {base}"] = "r"

    for wallet in result["wallets"]:
        code = wallet["currency_code"]
        table.add_row(
            [
                code,
                format_balance(wallet["balance"], code),
                f"{wallet['value']:.{VALUE_PRECISION}f}",
            ]
        )

    print(table)
    print(f"ИТОГО: {result['total']:,.{VALUE_PRECISION}f} {base}")


def handle_buy(
    options: dict[str, str | float],
    user: User,
) -> None:
    """Купить валюту и показать изменения баланса."""
    result = usecases.buy(
        user_id=user.user_id,
        currency_code=options[CURRENCY_OPTION],
        amount=options[AMOUNT_OPTION],
    )

    code = result["currency_code"]
    print(
        f"Покупка выполнена: {format_balance(result['amount'], code)} {code} "
        f"по курсу {result['rate']:.{VALUE_PRECISION}f} USD/{code}"
    )
    print("Изменения в портфеле:")
    print(
        f"- {code}: было {format_balance(result['before'], code)} "
        f"→ стало {format_balance(result['after'], code)}"
    )
    print(
        f"- USD: было {result['usd_before']:,.{VALUE_PRECISION}f} "
        f"→ стало {result['usd_after']:,.{VALUE_PRECISION}f}"
    )
    print(f"Оценочная стоимость покупки: {result['value']:,.{VALUE_PRECISION}f} USD")


def handle_sell(
    options: dict[str, str | float],
    user: User,
) -> None:
    """Продать валюту и показать изменения баланса."""
    result = usecases.sell(
        user_id=user.user_id,
        currency_code=options[CURRENCY_OPTION],
        amount=options[AMOUNT_OPTION],
    )

    code = result["currency_code"]
    print(
        f"Продажа выполнена: {format_balance(result['amount'], code)} {code} "
        f"по курсу {result['rate']:.{VALUE_PRECISION}f} USD/{code}"
    )
    print("Изменения в портфеле:")
    print(
        f"- {code}: было {format_balance(result['before'], code)} "
        f"→ стало {format_balance(result['after'], code)}"
    )
    print(f"Оценочная выручка: {result['value']:,.{VALUE_PRECISION}f} USD")
    print(
        f"Баланс USD: было {result['usd_before']:,.{VALUE_PRECISION}f} "
        f"→ стало {result['usd_after']:,.{VALUE_PRECISION}f}"
    )


def handle_get_rate(options: dict[str, str | float]) -> None:
    """Показать прямой и обратный курсы валют."""
    from_code = options[FROM_OPTION].strip().upper()
    to_code = options[TO_OPTION].strip().upper()

    rate, updated_at = usecases.get_rate(from_code, to_code)

    # В JSON остаётся ISO-дата в UTC; здесь меняется только её представление.
    updated = datetime.fromisoformat(updated_at)
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    display_date = updated.astimezone(timezone.utc).strftime(DISPLAY_DATETIME_FORMAT)
    # Малые курсы не обрезаем до двух знаков, даже для фиатных валют.
    precision = (
        RATE_PRECISION if rate < 1 or to_code in CRYPTO_CODES else VALUE_PRECISION
    )
    inverse_rate = 1 / rate
    inverse_precision = (
        RATE_PRECISION
        if inverse_rate < 1 or from_code in CRYPTO_CODES
        else VALUE_PRECISION
    )

    print(
        f"Курс {from_code}→{to_code}: {rate:.{precision}f} (обновлено: {display_date})"
    )
    print(f"Обратный курс {to_code}→{from_code}: {inverse_rate:.{inverse_precision}f}")
