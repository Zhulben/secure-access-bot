"""
Генераторы для создания ключей доступа и других случайных значений.
"""
import secrets
import string


# Алфавит для ключей: только заглавные буквы и цифры (читаемый вид)
_KEY_ALPHABET = string.ascii_uppercase + string.digits


def generate_key(prefix: str = "KEY", random_length: int = 12) -> str:
    """
    Сгенерировать случайный ключ доступа.

    Формат: PREFIX-XXXX-XXXX-XXXX (группы по 4 символа)

    Args:
        prefix: Префикс ключа (из конфига).
        random_length: Длина случайной части (кратно 4 для красоты, иначе последняя группа короче).

    Returns:
        Строка вида "KEY-AB12-CD34-EF56"
    """
    random_part = "".join(secrets.choice(_KEY_ALPHABET) for _ in range(random_length))

    # Разбить случайную часть на группы по 4
    groups = [random_part[i : i + 4] for i in range(0, len(random_part), 4)]
    suffix = "-".join(groups)

    return f"{prefix.upper()}-{suffix}"


def generate_short_token(length: int = 8) -> str:
    """
    Сгенерировать короткий токен (например, для временных ссылок).
    Использует URL-safe символы.
    """
    return secrets.token_urlsafe(length)[:length]
