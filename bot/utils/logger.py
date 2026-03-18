"""
Централизованная настройка логирования.
Один вызов setup_logging() настраивает всё приложение.
"""
import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Настроить корневой логгер.

    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR).
        log_file: Путь к файлу лога. Если None — только stdout.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Формат с временной меткой, уровнем и именем логгера
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt=fmt, datefmt=date_fmt)

    handlers: list[logging.Handler] = []

    # Вывод в stdout
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    # Опциональный файловый обработчик
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logging.basicConfig(
        level=numeric_level,
        handlers=handlers,
        force=True,  # Перезаписать уже установленные обработчики
    )

    # Заглушить чужие шумные логгеры
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Получить именованный логгер."""
    return logging.getLogger(name)
