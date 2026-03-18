from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import DATABASE_URL
from app.utils import now_utc

pool = AsyncConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
    open=False,
)


async def open_pool() -> None:
    await pool.open()


async def close_pool() -> None:
    await pool.close()


async def init_db() -> None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    tg_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    approved_at TIMESTAMPTZ
                )
                """
            )
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS access_keys (
                    id BIGSERIAL PRIMARY KEY,
                    key_hash TEXT NOT NULL UNIQUE,
                    valid_from TIMESTAMPTZ NOT NULL,
                    valid_to TIMESTAMPTZ NOT NULL,
                    created_by BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_access (
                    tg_id BIGINT PRIMARY KEY,
                    key_id BIGINT NOT NULL REFERENCES access_keys(id) ON DELETE CASCADE,
                    activated_at TIMESTAMPTZ NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS photos (
                    id BIGSERIAL PRIMARY KEY,
                    filename TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    photo_data BYTEA NOT NULL,
                    uploaded_by BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)")
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_access_keys_valid_to ON access_keys(valid_to)")
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_photos_created_at ON photos(created_at DESC)")
            await cur.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_key_id BIGINT REFERENCES access_keys(id) ON DELETE SET NULL"
            )
        await conn.commit()


async def upsert_user(
    tg_id: int,
    username: str | None,
    first_name: str,
    last_name: str,
    pending_key_id: int | None = None,
) -> None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO users (tg_id, username, first_name, last_name, status, pending_key_id)
                VALUES (%s, %s, %s, %s, 'pending', %s)
                ON CONFLICT (tg_id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    pending_key_id = EXCLUDED.pending_key_id
                """,
                (tg_id, username, first_name, last_name, pending_key_id),
            )
        await conn.commit()


async def get_user(tg_id: int) -> dict[str, Any] | None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT tg_id, username, first_name, last_name, status, created_at, approved_at, pending_key_id FROM users WHERE tg_id = %s",
                (tg_id,),
            )
            return await cur.fetchone()


async def set_user_status(tg_id: int, status: str) -> None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            if status == "approved":
                await cur.execute(
                    "UPDATE users SET status = %s, approved_at = NOW() WHERE tg_id = %s",
                    (status, tg_id),
                )
            else:
                await cur.execute("UPDATE users SET status = %s WHERE tg_id = %s", (status, tg_id))
        await conn.commit()


async def list_pending_users() -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT tg_id, username, first_name, last_name, created_at FROM users WHERE status = 'pending' ORDER BY created_at ASC"
            )
            return list(await cur.fetchall())


async def list_all_users() -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT tg_id, username, first_name, last_name, status, created_at FROM users ORDER BY created_at DESC"
            )
            return list(await cur.fetchall())


async def list_approved_users() -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT tg_id FROM users WHERE status = 'approved'")
            return list(await cur.fetchall())


async def list_users_with_valid_access() -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT tg_id FROM user_access WHERE expires_at >= NOW()"
            )
            return list(await cur.fetchall())


async def list_approved_without_access() -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT u.tg_id
                FROM users u
                LEFT JOIN user_access ua ON u.tg_id = ua.tg_id AND ua.expires_at >= NOW()
                WHERE u.status = 'approved' AND ua.tg_id IS NULL
                """
            )
            return list(await cur.fetchall())


async def invalidate_key_by_hash(key_hash: str) -> bool:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM access_keys WHERE key_hash = %s AND valid_to >= NOW()",
                (key_hash,),
            )
            deleted = cur.rowcount > 0
        await conn.commit()
    return deleted


async def replace_key(old_hash: str, new_hash: str, created_by: int, days: int = 7) -> bool:
    now = now_utc()
    valid_to = now + timedelta(days=days)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM access_keys WHERE key_hash = %s AND valid_to >= NOW()",
                (old_hash,),
            )
            if cur.rowcount == 0:
                return False
            await cur.execute(
                "INSERT INTO access_keys (key_hash, valid_from, valid_to, created_by) VALUES (%s, %s, %s, %s)",
                (new_hash, now, valid_to, created_by),
            )
        await conn.commit()
    return True


async def create_access_key(key_hash: str, created_by: int, days: int = 7) -> None:
    now = now_utc()
    valid_to = now + timedelta(days=days)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO access_keys (key_hash, valid_from, valid_to, created_by) VALUES (%s, %s, %s, %s)",
                (key_hash, now, valid_to, created_by),
            )
        await conn.commit()


async def find_active_key_by_hash(key_hash: str) -> dict[str, Any] | None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, valid_from, valid_to
                FROM access_keys
                WHERE key_hash = %s
                  AND valid_from <= NOW()
                  AND valid_to >= NOW()
                ORDER BY id DESC
                LIMIT 1
                """,
                (key_hash,),
            )
            return await cur.fetchone()


async def grant_daily_access(tg_id: int, key_id: int) -> None:
    activated_at = now_utc()
    expires_at = activated_at + timedelta(days=1)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO user_access (tg_id, key_id, activated_at, expires_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tg_id)
                DO UPDATE SET
                    key_id = EXCLUDED.key_id,
                    activated_at = EXCLUDED.activated_at,
                    expires_at = EXCLUDED.expires_at
                """,
                (tg_id, key_id, activated_at, expires_at),
            )
        await conn.commit()


async def has_valid_access(tg_id: int) -> bool:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM user_access WHERE tg_id = %s AND expires_at >= NOW()",
                (tg_id,),
            )
            return (await cur.fetchone()) is not None


async def get_access_info(tg_id: int) -> dict[str, Any] | None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT activated_at, expires_at FROM user_access WHERE tg_id = %s",
                (tg_id,),
            )
            return await cur.fetchone()


async def save_photo_to_db(filename: str, mime_type: str, photo_data: bytes, uploaded_by: int) -> None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO photos (filename, mime_type, photo_data, uploaded_by) VALUES (%s, %s, %s, %s)",
                (filename, mime_type, photo_data, uploaded_by),
            )
        await conn.commit()


async def get_latest_photo_from_db() -> dict[str, Any] | None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, filename, mime_type, photo_data, created_at FROM photos ORDER BY id DESC LIMIT 1"
            )
            return await cur.fetchone()
