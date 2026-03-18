"""Initial schema: users, access_keys, key_usages, approval_requests, broadcasts, delivery_logs

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- access_keys (создаём раньше users, т.к. users ссылается на него) ---
    op.create_table(
        "access_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key_value", sa.String(length=128), nullable=False),
        sa.Column("key_type", sa.String(length=16), nullable=False),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_keys_key_value", "access_keys", ["key_value"], unique=True)

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("tg_first_name", sa.String(length=64), nullable=True),
        sa.Column("tg_last_name", sa.String(length=64), nullable=True),
        sa.Column("entered_first_name", sa.String(length=64), nullable=True),
        sa.Column("entered_last_name", sa.String(length=64), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("access_key_id", sa.Integer(), nullable=True),
        sa.Column("key_entered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["access_key_id"], ["access_keys.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.create_index("ix_users_status", "users", ["status"])

    # Теперь можно добавить FK в access_keys → users
    op.create_foreign_key(
        "fk_access_keys_created_by_admin_id",
        "access_keys", "users",
        ["created_by_admin_id"], ["id"],
        ondelete="SET NULL",
    )

    # --- key_usages ---
    op.create_table(
        "key_usages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["key_id"], ["access_keys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- approval_requests ---
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("processed_by", sa.Integer(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["key_id"], ["access_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["processed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_user_id", "approval_requests", ["user_id"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])

    # --- broadcasts ---
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=True),
        sa.Column("broadcast_type", sa.String(length=24), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("photo_file_id", sa.String(length=256), nullable=True),
        sa.Column("send_to_pending_masked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- delivery_logs ---
    op.create_table(
        "delivery_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("broadcast_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("delivery_mode", sa.String(length=16), nullable=False),
        sa.Column("delivery_status", sa.String(length=16), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["broadcast_id"], ["broadcasts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delivery_logs_broadcast_id", "delivery_logs", ["broadcast_id"])


def downgrade() -> None:
    op.drop_table("delivery_logs")
    op.drop_table("broadcasts")
    op.drop_table("approval_requests")
    op.drop_table("key_usages")
    op.drop_constraint("fk_access_keys_created_by_admin_id", "access_keys", type_="foreignkey")
    op.drop_table("users")
    op.drop_table("access_keys")
