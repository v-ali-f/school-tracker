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
