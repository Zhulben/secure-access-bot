"""
Конфигурация приложения.
Все параметры читаются из переменных окружения через pydantic-settings.
"""
from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Настройки приложения из .env файла."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram Bot
    bot_token: str

    # База данных
    database_url: str

    # Администраторы (список telegram_id через запятую: "123456,789012")
    admin_ids: str = ""

    # Уровень логирования (DEBUG, INFO, WARNING, ERROR)
    log_level: str = "INFO"

    # Префикс для генерируемых ключей
    key_prefix: str = "KEY"

    # Длина случайной части ключа (символов)
    key_random_length: int = 12

    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        v = v.strip()
        if not v or ":" not in v:
            raise ValueError("BOT_TOKEN некорректен. Проверьте формат: 123456789:ABC...")
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("postgresql+asyncpg://", "postgresql://", "postgres://")):
            raise ValueError(
                "DATABASE_URL должен начинаться с postgresql+asyncpg:// "
                "Пример: postgresql+asyncpg://user:pass@localhost:5432/dbname"
            )
        # asyncpg требует схему postgresql+asyncpg://
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    def get_admin_ids(self) -> set[int]:
        """Вернуть множество telegram_id администраторов."""
        if not self.admin_ids.strip():
            return set()
        ids = set()
        for raw in self.admin_ids.split(","):
            raw = raw.strip()
            if raw.isdigit():
                ids.add(int(raw))
        return ids


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Получить единственный экземпляр конфигурации (синглтон)."""
    return Config()
