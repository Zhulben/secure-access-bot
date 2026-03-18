"""Пакет middlewares: инъекция сессии, защита админ-роутов."""
from bot.middlewares.admin import AdminMiddleware
from bot.middlewares.db import DatabaseMiddleware

__all__ = ["DatabaseMiddleware", "AdminMiddleware"]
