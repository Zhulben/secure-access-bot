from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
TZ = os.getenv("TZ", "Europe/Amsterdam")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS не найдены в .env")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден в .env")
