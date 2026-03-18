"""
Валидаторы пользовательского ввода.
Возвращают (True, cleaned_value) или (False, error_message).
"""
import re
from typing import Optional


# Допустимые символы в имени/фамилии
_NAME_PATTERN = re.compile(r"^[А-Яа-яЁёA-Za-z\s\-']{2,64}$")

# Ключ: буквы, цифры, дефис, нижнее подчёркивание (2–128 символов)
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9\-_]{2,128}$")


def validate_name(value: str) -> tuple[bool, str]:
    """
    Проверить имя или фамилию.

    Returns:
        (True, очищенное_значение) или (False, сообщение_об_ошибке)
    """
    cleaned = value.strip()
    if not cleaned:
        return False, "Поле не может быть пустым."
    if len(cleaned) < 2:
        return False, "Слишком короткое значение (минимум 2 символа)."
    if len(cleaned) > 64:
        return False, "Слишком длинное значение (максимум 64 символа)."
    if not _NAME_PATTERN.match(cleaned):
        return False, (
            "Допустимы только буквы (русские и латинские), пробелы, дефис и апостроф."
        )
    return True, cleaned


def validate_key_value(value: str) -> tuple[bool, str]:
    """
    Проверить значение ключа доступа.

    Returns:
        (True, очищенное_значение) или (False, сообщение_об_ошибке)
    """
    cleaned = value.strip().upper()
    if not cleaned:
        return False, "Ключ не может быть пустым."
    if len(cleaned) < 2:
        return False, "Ключ слишком короткий (минимум 2 символа)."
    if len(cleaned) > 128:
        return False, "Ключ слишком длинный (максимум 128 символов)."
    # Ключи могут содержать буквы, цифры и дефис (с учётом формата PREFIX-XXXX-XXXX)
    if not re.match(r"^[A-Z0-9\-_]{2,128}$", cleaned):
        return False, "Ключ должен содержать только латинские буквы, цифры и дефисы."
    return True, cleaned


def validate_usage_limit(value: str) -> tuple[bool, Optional[int]]:
    """
    Проверить лимит использований ключа.
    '0' или пустая строка — безлимит (None).

    Returns:
        (True, int_or_None) или (False, None)
    """
    cleaned = value.strip()
    if not cleaned or cleaned == "0":
        return True, None  # Безлимит
    if not cleaned.isdigit():
        return False, None
    limit = int(cleaned)
    if limit < 1:
        return False, None
    if limit > 100_000:
        return False, None
    return True, limit


def validate_broadcast_text(value: str) -> tuple[bool, str]:
    """
    Проверить текст рассылки.

    Returns:
        (True, text) или (False, error_message)
    """
    text = value.strip()
    if not text:
        return False, "Текст рассылки не может быть пустым."
    if len(text) > 4096:
        return False, f"Текст слишком длинный ({len(text)} / 4096 символов)."
    return True, text
