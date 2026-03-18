# ============================================================
# Dockerfile для secure_access_bot
# ============================================================

# Базовый образ: компактный Python 3.12 slim
FROM python:3.12-slim

# Метаданные
LABEL maintainer="secure_access_bot"
LABEL description="Telegram бот управления доступом"

# Рабочая директория внутри контейнера
WORKDIR /app

# Установка системных зависимостей (нужны для asyncpg)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Сначала копируем только requirements.txt для кэширования слоёв Docker
COPY requirements.txt .

# Установка зависимостей Python
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Создать непривилегированного пользователя для безопасности
RUN adduser --disabled-password --gecos "" botuser \
    && chown -R botuser:botuser /app

USER botuser

# Путь для импорта пакета bot при запуске alembic
ENV PYTHONPATH=/app

# По умолчанию — запуск бота
CMD ["python", "-m", "bot.main"]
