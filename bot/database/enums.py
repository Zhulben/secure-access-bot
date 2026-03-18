"""
Перечисления (Enum) для всех справочных типов БД.
Использует Python enum + PostgreSQL native enum через SQLAlchemy.
"""
import enum


class UserRole(str, enum.Enum):
    """Роль пользователя в системе."""
    USER = "user"
    ADMIN = "admin"


class UserStatus(str, enum.Enum):
    """Статус пользователя в процессе верификации."""
    PENDING = "pending"       # Ожидает одобрения
    APPROVED = "approved"     # Одобрен, имеет доступ
    REJECTED = "rejected"     # Отклонён
    BANNED = "banned"         # Заблокирован


class KeyType(str, enum.Enum):
    """Тип ключа доступа."""
    REUSABLE = "reusable"     # Многоразовый
    ONE_TIME = "one_time"     # Одноразовый


class RequestStatus(str, enum.Enum):
    """Статус заявки на доступ."""
    PENDING = "pending"       # На рассмотрении
    APPROVED = "approved"     # Одобрена
    REJECTED = "rejected"     # Отклонена


class BroadcastType(str, enum.Enum):
    """Тип рассылки."""
    TEXT = "text"                     # Только текст
    PHOTO = "photo"                   # Только фото
    PHOTO_CAPTION = "photo_caption"   # Фото с подписью


class DeliveryMode(str, enum.Enum):
    """Режим доставки сообщения пользователю."""
    REAL = "real"       # Реальное содержимое
    MASKED = "masked"   # Маскированное (для pending-пользователей)
    SKIPPED = "skipped" # Пропущено (бан, ошибка и т.д.)


class DeliveryStatus(str, enum.Enum):
    """Результат доставки."""
    SUCCESS = "success"
    FAILED = "failed"
