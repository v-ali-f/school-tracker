# Архитектура v43

## Ядро сущностей
- `AcademicYear`
- `SchoolClass`
- `Child`
- `User`
- `Incident`
- `ControlWork`
- `ChildMovement`
- `SupportCase`
- `SystemLog`

## Целевая структура проекта
```text
app/
  config.py
  extensions.py
  models/
  routes/
  services/
  utils/
  templates/
  static/
```

## Правило развития
Текущие рабочие модули не ломаем. Перенос идёт постепенно:
1. Сначала выносим общие сервисы.
2. Потом создаём новые модули уже по правильной структуре.
3. После стабилизации переносим старые Blueprint по одному.

## Рекомендуемый порядок дальнейшего выноса
1. dashboard
2. control_works
3. classes
4. children
5. documents
6. incidents
7. users
