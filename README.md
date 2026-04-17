# school-tracker — внутренняя система школы №547

Веб-приложение для учёта инцидентов, социально-психологического сопровождения, работы с контингентом учеников и управленческих отчётов. Работает в школе с 31.03.2026.

**Актуальность копии:** 17.04.2026. История изменений начиная с первой выгрузки — в [CHANGELOG.md](CHANGELOG.md).

## Что умеет система

**Учёт инцидентов:**
- Регистрация случаев (травмы, вызов скорой, драки, буллинг, дисциплина и т. д.).
- Дашборд с графиками по категориям / зданиям / классам / статусам.
- Реестр с фильтрами, переключением вида table / list, выбором отображаемых колонок.
- Раздел «Мои заявки» для любого пользователя — то, что он сам завёл.

**Контингент:**
- Справочник учеников с поиском по ФИО (триграммный индекс в PostgreSQL).
- Зачисления / отчисления / движение по классам.
- Импорт из Excel-выгрузок АИС.

**Соц.-псих. служба:**
- Социальные паспорта учеников (семья, условия, категории).
- Регистр паспортов, дашборд.
- Пропуски занятий, уважительные / неуважительные причины.
- Задачи и поручения между специалистами.

**Методика и администрация:**
- МЦКО-диагностики.
- Олимпиады школьного тура + аналитика.
- Контрольные работы.
- Реестр приказов.
- Кафедры и нагрузка.

**Права и роли:**
- `ADMIN` — полный доступ.
- `CLASS_TEACHER` — свой класс, «Мои заявки», «Мои задачи», соц. паспорта своих учеников.
- `TEACHER` — только базовые реестры и создание инцидентов.
- `PSYCHOLOGIST` — соц.-псих. блок + реестр инцидентов.
- `SOCIAL_PEDAGOG` — расширенный набор: пропуска, паспорта, МЦКО, олимпиады, контрольные, приказы.
- `METHODIST` — методический блок + дашборды.
- `KPP` — контрольно-пропускной пункт.
- `DEPUTY_DIRECTOR` — по объёму близок к `ADMIN`, без служебных админских действий.

Детальная матрица видимости разделов — ниже.

## Стек

- Python 3.10+, Flask, SQLAlchemy, Flask-Login, Flask-WTF
- PostgreSQL (продакшн) / SQLite (локально — в этой копии)
- Jinja2 + Bootstrap 5
- WeasyPrint для PDF-отчётов (опционально)

## Быстрый запуск

Подробная пошаговая инструкция — [SETUP.md](SETUP.md).

Коротко:

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
flask --app run init-db
flask --app run repair-runtime-columns
flask --app run seed-academic-year
flask --app run seed-olympiads
python init_admin.py      # создаст admin / admin123
python run.py             # http://localhost:5001
```

Тестовые пользователи для проверки ролей: `python seed_test_data.py` (список — в SETUP.md).

## Структура

```
run.py / app/__init__.py / app/config.py
app/models_legacy.py        → главные модели (Incident, Child, User, Role ...)
app/permissions.py          → матрица прав: has_permission(), has_role(), is_admin()
app/children.py             → дети, инциденты, соц. паспорт, contingent
app/modules/hub/routes.py   → главная страница, фильтрация секций по ролям
app/core/context_processors.py → уведомления + авто-хлебные крошки
app/role_access_admin.py    → настройка доступа по ролям (/admin/role-access)
app/service_staff.py        → сопровождение, задачи/поручения
app/tasks.py + app/modules/tasks/ → модуль задач
app/templates/              → Jinja2 HTML
app/static/css/app.css      → стили
migrations/                 → вспомогательные скрипты миграций
fonts/                      → шрифты для PDF
```

## Матрица видимости разделов

| Раздел | ADMIN | CLASS_TEACHER | TEACHER | PSYCHOLOGIST | SOCIAL_PEDAGOG | METHODIST |
|--------|:-----:|:-------------:|:-------:|:------------:|:--------------:|:---------:|
| Кафедры | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Диагностики МЦКО | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Пропуска | ✓ | ✓ | — | — | ✓ | — |
| Основные реестры | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Контрольные работы | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Олимпиады | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Реестр приказов | ✓ | — | — | — | ✓ | ✓ |
| Классное руководство | ✓ | ✓ | — | — | ✓ | ✓ |
| Соц-псих служба | ✓ | — | — | ✓ | ✓ | ✓ |
| Управленческий контур | ✓ | — | — | — | ✓ | ✓ |

## Переменные окружения

- `SECRET_KEY` — ключ сессий Flask.
- `DATABASE_URL` — строка подключения SQLAlchemy. По умолчанию — SQLite (`app.db` в корне). Для PostgreSQL: `postgresql+psycopg2://user:password@localhost/school_tracker`.
- `UPLOAD_FOLDER` — папка для документов (по умолчанию `uploads/`).
- `MAX_CONTENT_LENGTH` — лимит загрузки файла в байтах (по умолчанию 200 МБ).

## Переход на PostgreSQL

1. Создать пустую базу `school_tracker`.
2. Указать `DATABASE_URL=postgresql+psycopg2://user:pass@localhost/school_tracker` в `.env`.
3. Доустановить драйвер: `pip install psycopg2-binary` (на Mac M1/M2 может потребоваться `brew install postgresql`).
4. `flask --app run init-db` → `flask --app run repair-runtime-columns`.

## Резервное копирование

PostgreSQL:

```bash
pg_dump -Fc school_tracker > backup.dump
pg_restore -d school_tracker backup.dump
```

SQLite: скопировать файл `app.db` — это вся база.

## Обновление копии

Когда в репозитории появляется новая версия:

```bash
git pull
pip install -r requirements.txt
flask --app run repair-runtime-columns
```

Папка `uploads/` и файл `app.db` остаются локальными, `.gitignore` их исключает.

## История изменений

См. [CHANGELOG.md](CHANGELOG.md) — подробный список правок начиная с 6 апреля 2026 г. Разбит по датам и сессиям работы.
