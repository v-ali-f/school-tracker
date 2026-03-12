# school-tracker v62

Архитектурно переработанная версия проекта по ТЗ v62.

## Что изменено
- app/__init__.py оставлен только как фабрика приложения
- единая точка расширений перенесена в app/core/extensions.py
- регистрация blueprint вынесена в app/core/module_registry.py
- context processors вынесены в app/core/context_processors.py
- добавлен пакет app/models/ с переходным разбиением моделей по доменам
- runtime-ремонт схемы и seed вынесены в CLI-команды
- добавлены instance/, uploads/, data_seed/, tests/

## Первый запуск
1. Скопировать .env.example в .env
2. Заполнить DATABASE_URL
3. Установить зависимости: pip install -r requirements.txt
4. Выполнить: flask init-db ; flask repair-runtime-columns ; flask seed-olympiads ; flask seed-academic-year
5. Запуск: python run.py

## Важно
В v62 сохранён compatibility-layer. Старые плоские модули пока не удалены полностью, а остаются как переходный слой до полного переноса в app/modules/.
