# school-tracker v63

Версия v63 завершает архитектурный переход в безопасном compatibility-режиме.

## Быстрый запуск

1. Создайте файл `.env` по образцу `.env.example`.
2. Установите зависимости:
   `pip install -r requirements.txt`
3. Выполните миграции:
   `flask db upgrade`
4. Инициализируйте стартовые данные:
   `flask seed-initial-data`
5. Создайте администратора:
   `flask create-admin --username admin --password admin123`
6. При необходимости создайте текущий учебный год:
   `flask seed-academic-year --name 2025/2026`
7. Запустите приложение:
   `python run.py`

## Команды CLI

- `flask init-db`
- `flask db upgrade`
- `flask db migrate -m "message"`
- `flask seed-initial-data`
- `flask create-admin`
- `flask repair-runtime-columns`
- `flask seed-olympiads`
- `flask seed-academic-year`

## Архитектура

Канонический слой моделей находится в `app/models/`.
Переходный compatibility-слой находится в `app/models_legacy.py`.
Основные legacy-blueprint-файлы сохранены, но используются как временный слой до полного переноса доменных модулей.

## Обновление существующей базы

1. Сделайте резервную копию базы.
2. Обновите код проекта.
3. Выполните `flask db upgrade`.
4. Только в аварийном случае выполните `flask repair-runtime-columns`.

## Новая чистая база

1. Создайте БД и укажите `DATABASE_URL` в `.env`.
2. Выполните `flask db upgrade`.
3. Выполните `flask seed-initial-data`.
4. Выполните `flask create-admin`.
