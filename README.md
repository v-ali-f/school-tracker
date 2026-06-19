# school-tracker v64

Версия v64 направлена на стабилизацию архитектуры, запуск без ручной правки импортов и развитие олимпиадного/аналитического блока.

## Быстрый запуск

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Приложение использует `run.py` как точку входа.

## Переменные окружения

- `SECRET_KEY`
- `DATABASE_URL` — строка подключения SQLAlchemy. Для PostgreSQL пример: `postgresql+psycopg2://user:password@localhost/school_tracker`
- `UPLOAD_FOLDER` — внешняя папка для документов
- `MAX_CONTENT_LENGTH` — лимит загрузки файлов в байтах. По умолчанию 200 МБ
- `APP_BASE_URL` — внешний адрес портала. Для PWA и web push должен быть `https://...`
- `FIREBASE_SERVICE_ACCOUNT_FILE` — путь к service account JSON для отправки push
- `FIREBASE_WEB_API_KEY`
- `FIREBASE_WEB_AUTH_DOMAIN`
- `FIREBASE_WEB_PROJECT_ID`
- `FIREBASE_WEB_STORAGE_BUCKET`
- `FIREBASE_WEB_MESSAGING_SENDER_ID`
- `FIREBASE_WEB_APP_ID`
- `FIREBASE_WEB_MEASUREMENT_ID` — необязательно
- `FIREBASE_WEB_VAPID_KEY`
- `PWA_BADGE_POLL_INTERVAL_MS` — интервал обновления счетчика badge, по умолчанию 60000 мс

## PWA

Проект переведён на web-first схему: мобильный сценарий теперь развивается как PWA поверх основного портала.

- Установка на телефон и фоновый web push требуют `HTTPS`
- счетчик непрочитанных на иконке зависит от поддержки браузера
- серверный слой для PWA использует существующие `/mobile/api/*` endpoints

## Продакшн

В репозитории есть два готовых варианта развертывания:

- прямой внешний контур на одном сервере: [deploy/altair-school/README.md](/Users/aleksandr/Documents/Школьный портал/school-tracker/deploy/altair-school/README.md)
- текущая схема `VPS -> WireGuard -> школьный сервер`: [deploy/altair-edu/README.md](/Users/aleksandr/Documents/Школьный портал/school-tracker/deploy/altair-edu/README.md)

Для текущего домена `altair-edu.ru` добавлены:

- [deploy/altair-edu/nginx/altair-edu.ru.conf](/Users/aleksandr/Documents/Школьный портал/school-tracker/deploy/altair-edu/nginx/altair-edu.ru.conf)
- [.env.production.example](/Users/aleksandr/Documents/Школьный портал/school-tracker/.env.production.example)

## Flask CLI

```bash
flask --app run init-db
flask --app run seed-initial-data
flask --app run create-admin
flask --app run seed-olympiads
flask --app run seed-academic-year
flask --app run repair-runtime-columns
```

## PostgreSQL

1. Создайте пустую базу `school_tracker`.
2. Укажите `DATABASE_URL`.
3. Выполните `flask --app run init-db`.
4. Выполните `flask --app run repair-runtime-columns`.

## Обновление через GitHub

```bash
git pull
pip install -r requirements.txt
flask --app run repair-runtime-columns
```

Папка `uploads/` должна лежать вне git-репозитория или быть исключена `.gitignore`.

## Резервное копирование

Для PostgreSQL:

```bash
pg_dump -Fc school_tracker > backup.dump
pg_restore -d school_tracker backup.dump
```

## Что добавлено в v64

- более строгий слой `app/models/*` без wildcard-обёрток по доменам
- новый раздел `/analytics`
- основа рейтинга учителей `app/services/teacher_rating.py`
- безопасные сообщения ошибок CLI
- обновлённые служебные файлы проекта
