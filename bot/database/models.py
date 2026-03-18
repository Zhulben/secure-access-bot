"""
ORM-модели для всех таблиц БД.
Все модели наследуют Base и используют mapped_column (SQLAlchemy 2.x style).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base, utcnow
from bot.database.enums import (
    BroadcastType,
    DeliveryMode,
    DeliveryStatus,
    KeyType,
    RequestStatus,
    UserRole,
    UserStatus,
)


class User(Base):
    """Пользователь Telegram."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Данные из Telegram
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tg_first_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tg_last_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Данные, введённые пользователем при регистрации
    entered_first_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entered_last_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Роль и статус
    role: Mapped[UserRole] = mapped_column(
        String(16), default=UserRole.USER, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        String(16), default=UserStatus.PENDING, nullable=False, index=True
    )

    # Ключ доступа
    access_key_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("access_keys.id", ondelete="SET NULL"), nullable=True
    )
    key_entered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Временные метки статусов
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # created_at / updated_at — унаследованы от Base

    # Связи
    access_key: Mapped[Optional["AccessKey"]] = relationship(
        "AccessKey", foreign_keys=[access_key_id], back_populates="users"
    )
    key_usages: Mapped[list["KeyUsage"]] = relationship(
        "KeyUsage", back_populates="user", cascade="all, delete-orphan"
    )
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(
        "ApprovalRequest",
        foreign_keys="ApprovalRequest.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    delivery_logs: Mapped[list["DeliveryLog"]] = relationship(
        "DeliveryLog", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} tg_id={self.telegram_id} status={self.status}>"

    @property
    def full_name(self) -> str:
        """Введённое пользователем ФИО либо имя из Telegram."""
        if self.entered_first_name or self.entered_last_name:
            parts = filter(None, [self.entered_first_name, self.entered_last_name])
            return " ".join(parts)
        parts = filter(None, [self.tg_first_name, self.tg_last_name])
        return " ".join(parts) or f"tg:{self.telegram_id}"

    @property
    def display_name(self) -> str:
        """Имя для отображения в интерфейсе."""
        name = self.full_name
        if self.username:
            return f"{name} (@{self.username})"
        return name


class AccessKey(Base):
    """Ключ доступа для регистрации пользователей."""

    __tablename__ = "access_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_value: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    key_type: Mapped[KeyType] = mapped_column(String(16), nullable=False)

    # Кто создал ключ
    created_by_admin_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Срок действия
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Активность и лимиты
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    usage_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = безлимит
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # created_at / updated_at — унаследованы от Base

    # Связи
    created_by_admin: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_admin_id]
    )
    users: Mapped[list["User"]] = relationship(
        "User", foreign_keys="User.access_key_id", back_populates="access_key"
    )
    key_usages: Mapped[list["KeyUsage"]] = relationship(
        "KeyUsage", back_populates="key", cascade="all, delete-orphan"
    )
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(
        "ApprovalRequest",
        foreign_keys="ApprovalRequest.key_id",
        back_populates="key",
    )

    def __repr__(self) -> str:
        return f"<AccessKey id={self.id} value={self.key_value} type={self.key_type}>"

    @property
    def is_exhausted(self) -> bool:
        """Исчерпан ли лимит использований."""
        if self.usage_limit is None:
            return False
        return self.usage_count >= self.usage_limit

    @property
    def is_expired(self) -> bool:
        """Истёк ли срок действия."""
        from datetime import timezone
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


class KeyUsage(Base):
    """Журнал использования ключей."""

    __tablename__ = "key_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("access_keys.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )

    # Переопределяем — у этой таблицы нет updated_at, только used_at
    updated_at: Mapped[Optional[datetime]] = mapped_column(  # type: ignore[assignment]
        DateTime(timezone=True), nullable=True
    )

    # Связи
    key: Mapped["AccessKey"] = relationship("AccessKey", back_populates="key_usages")
    user: Mapped["User"] = relationship("User", back_populates="key_usages")

    def __repr__(self) -> str:
        return f"<KeyUsage key_id={self.key_id} user_id={self.user_id}>"


class ApprovalRequest(Base):
    """Заявка пользователя на получение доступа."""

    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("access_keys.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[RequestStatus] = mapped_column(
        String(16), default=RequestStatus.PENDING, nullable=False, index=True
    )

    # Кто обработал заявку (admin user.id)
    processed_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # created_at унаследован от Base; updated_at тоже, но здесь менее актуален
    updated_at: Mapped[Optional[datetime]] = mapped_column(  # type: ignore[assignment]
        DateTime(timezone=True), nullable=True
    )

    # Связи
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="approval_requests"
    )
    key: Mapped[Optional["AccessKey"]] = relationship(
        "AccessKey", foreign_keys=[key_id], back_populates="approval_requests"
    )
    processed_by_admin: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[processed_by]
    )

    def __repr__(self) -> str:
        return f"<ApprovalRequest id={self.id} user_id={self.user_id} status={self.status}>"


class Broadcast(Base):
    """Рассылка, созданная администратором."""

    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    broadcast_type: Mapped[BroadcastType] = mapped_column(String(24), nullable=False)

    # Контент
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Настройки рассылки
    send_to_pending_masked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_highlighted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # created_at унаследован от Base
    updated_at: Mapped[Optional[datetime]] = mapped_column(  # type: ignore[assignment]
        DateTime(timezone=True), nullable=True
    )

    # Связи
    admin: Mapped[Optional["User"]] = relationship("User", foreign_keys=[admin_id])
    delivery_logs: Mapped[list["DeliveryLog"]] = relationship(
        "DeliveryLog", back_populates="broadcast", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Broadcast id={self.id} type={self.broadcast_type}>"


class DeliveryLog(Base):
    """Журнал доставки сообщений рассылки."""

    __tablename__ = "delivery_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("broadcasts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    delivery_mode: Mapped[DeliveryMode] = mapped_column(String(16), nullable=False)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(String(16), nullable=False)
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )

    # Переопределяем — у этой таблицы нет updated_at
    updated_at: Mapped[Optional[datetime]] = mapped_column(  # type: ignore[assignment]
        DateTime(timezone=True), nullable=True
    )

    # Связи
    broadcast: Mapped["Broadcast"] = relationship("Broadcast", back_populates="delivery_logs")
    user: Mapped["User"] = relationship("User", back_populates="delivery_logs")

    def __repr__(self) -> str:
        return (
            f"<DeliveryLog broadcast={self.broadcast_id} "
            f"user={self.user_id} status={self.delivery_status}>"
        )


class ViewerCode(Base):
    """Глобальный код просмотра рассылок."""

    __tablename__ = "viewer_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False)

    # updated_at не нужен
    updated_at: Mapped[Optional[datetime]] = mapped_column(  # type: ignore[assignment]
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<ViewerCode code={self.code}>"
