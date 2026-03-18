# Secure Access Bot

Telegram-бот для управления доступом к закрытому контенту.

## Возможности

- Регистрация пользователей с ключом доступа
- Ручное одобрение/отклонение заявок администратором
- Бан и разбан пользователей
- Создание и управление ключами доступа (одноразовые / многоразовые)
- Рассылка сообщений (текст, фото, фото с подписью)
- Опциональные masked-уведомления для pending-пользователей
- Полный аудит-лог действий
- Docker-ready с PostgreSQL

---

## Структура проекта

```
secure_access_bot/
├── bot/
│   ├── config.py           # Настройки из .env
│   ├── main.py             # Точка входа
│   ├── handlers/           # Обработчики aiogram
│   ├── keyboards/          # Reply и Inline клавиатуры
│   ├── states/             # FSM состояния
│   ├── services/           # Бизнес-логика
│   ├── database/           # Модели SQLAlchemy
│   ├── middlewares/        # Middleware (DB, Admin)
│   └── utils/              # Утилиты
├── alembic/                # Миграции БД
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Быстрый старт (локально)

### Требования

- Python 3.12+
- PostgreSQL 14+

### 1. Клонировать / скачать проект

```bash
git clone https://github.com/yourname/secure_access_bot.git
cd secure_access_bot
```

### 2. Создать виртуальное окружение

```bash
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Создать .env

```bash
cp .env.example .env
```

Отредактировать `.env`:

```env
BOT_TOKEN=ваш_токен_от_BotFather
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/secure_access_bot
ADMIN_IDS=ваш_telegram_id
LOG_LEVEL=INFO
```

### 5. Создать базу данных

```bash
createdb secure_access_bot
```

или через psql:

```sql
CREATE DATABASE secure_access_bot;
CREATE USER botuser WITH PASSWORD 'botpassword';
GRANT ALL PRIVILEGES ON DATABASE secure_access_bot TO botuser;
```

### 6. Применить миграции

```bash
alembic upgrade head
```

### 7. Запустить бота

```bash
python -m bot.main
```

---

## Запуск через Docker Compose

### 1. Создать .env

```bash
cp .env.example .env
# Отредактировать: указать BOT_TOKEN и ADMIN_IDS
```

В `.env` для Docker оставьте:

```env
DATABASE_URL=postgresql+asyncpg://botuser:botpassword@postgres:5432/secure_access_bot
```

(хост `postgres` — это имя сервиса в docker-compose.yml)

### 2. Запустить

```bash
docker compose up -d --build
```

Это запустит:
- `postgres` — PostgreSQL база данных
- `migrate` — применит миграции Alembic
- `bot` — сам бот

### 3. Проверить статус

```bash
docker compose ps
```

### 4. Посмотреть логи

```bash
# Все сервисы
docker compose logs -f

# Только бот
docker compose logs -f bot

# Только postgres
docker compose logs -f postgres
```

### 5. Остановить

```bash
docker compose down
```

### 6. Остановить и удалить данные БД

```bash
docker compose down -v
```

---

## Деплой на VPS

### Требования к серверу

- Ubuntu 22.04 / Debian 12
- Docker + Docker Compose Plugin
- Минимум 512 МБ RAM

### Шаги деплоя

#### 1. Установить Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

#### 2. Скачать проект

```bash
# Через git (рекомендуется)
git clone https://github.com/yourname/secure_access_bot.git
cd secure_access_bot

# Или через scp/rsync с локальной машины:
# scp -r ./secure_access_bot user@your-vps-ip:/home/user/
```

#### 3. Создать .env

```bash
cp .env.example .env
nano .env   # Заполнить BOT_TOKEN, ADMIN_IDS
```

#### 4. Запустить

```bash
docker compose up -d --build
```

#### 5. Проверить

```bash
docker compose ps
docker compose logs -f bot
```

---

## Обновление проекта на VPS

```bash
# 1. Зайти на VPS
ssh user@your-vps-ip
cd secure_access_bot

# 2. Получить изменения
git pull origin main

# 3. Пересобрать и перезапустить контейнеры
docker compose up -d --build

# 4. Применить новые миграции (если есть)
docker compose run --rm migrate

# 5. Проверить логи
docker compose logs -f bot
```

---

## Команды для работы с миграциями

```bash
# Применить все миграции
alembic upgrade head

# Применить через Docker
docker compose run --rm migrate

# Откатить последнюю миграцию
alembic downgrade -1

# Посмотреть текущую версию
alembic current

# Создать новую миграцию (autogenerate)
alembic revision --autogenerate -m "описание изменений"

# Посмотреть историю миграций
alembic history
```

---

## Команды для диагностики

```bash
# Статус контейнеров
docker compose ps

# Логи в реальном времени
docker compose logs -f bot

# Подключиться к контейнеру бота
docker compose exec bot bash

# Подключиться к PostgreSQL
docker compose exec postgres psql -U botuser -d secure_access_bot

# Перезапустить только бот
docker compose restart bot

# Проверить использование ресурсов
docker stats
```

---

## Инициализация git и публикация

```bash
# Инициализировать git (если не клонировали)
cd secure_access_bot
git init
git add .
git commit -m "Initial commit"

# Создать репозиторий на GitHub через веб-интерфейс, затем:
git remote add origin https://github.com/yourname/secure_access_bot.git
git branch -M main
git push -u origin main
```

**Важно:** файл `.env` добавлен в `.gitignore` и не попадёт в репозиторий.

---

## Автоперезапуск

В `docker-compose.yml` уже настроен `restart: always` для сервисов `postgres` и `bot`.
Это означает, что контейнеры автоматически перезапустятся:
- После перезагрузки сервера
- При аварийном завершении процесса

Для автозапуска Docker при старте системы:

```bash
sudo systemctl enable docker
```

---

## Описание команд бота

### Команды пользователя

| Команда | Описание |
|---------|----------|
| `/start` | Начало работы / регистрация |
| `/help` | Справка |
| `/cancel` | Отменить текущее действие |

### Команды администратора

| Команда | Описание |
|---------|----------|
| `/admin` | Открыть панель администратора |
| `/newkey` | Создать новый ключ доступа |
| `/finduser` | Найти пользователя |

---

## Возможные улучшения

1. **Redis для FSM** — заменить `MemoryStorage` на `RedisStorage` для надёжности при перезапусках
2. **Webhook вместо polling** — для production-окружения с низкой задержкой
3. **Роль moderator** — промежуточная роль между user и admin
4. **Экспорт пользователей** — выгрузка списка в CSV/Excel
5. **Telegram Mini App** — веб-панель управления
6. **Уведомления на почту** — дублирование важных событий на email
7. **Rate limiting** — ограничение частоты запросов от одного пользователя
8. **Scheduled broadcasts** — рассылки по расписанию через APScheduler
9. **Двухфакторная верификация** — OTP или реферальная система
10. **Мониторинг** — интеграция с Prometheus/Grafana через aiogram-metrics
