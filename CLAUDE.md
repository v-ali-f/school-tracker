# school-tracker — школа №547

Внутренняя система. Flask + PostgreSQL. В эксплуатации, логины розданы 31.03.2026.

## Сессия 60b (24.04.2026) — ЗАДЕПЛОЕНО 24.04.2026

Распространение гибких уведомлений на задачи (вариант A классификации).
5 файлов, `../deploy_session60b.py`, бэкапы `.bak_session60b`, smoke OK
(login 200, admin `/profile/notifications` 200 с 4+4 радио).

- **БД.** Новая колонка `"user".notify_task_mode VARCHAR(20) DEFAULT 'all'`
  (`models_legacy.py` + `bootstrap.py` ALTER).
- **`tasks._deliver_notifications`.** Добавлены `_TASK_NOTIFY_EVENT_CLASS` и
  `_task_mode_allows()`. Перед `db.session.add(TaskNotification(...))` — если
  режим пользователя не пропускает событие, recipient пропускается (касается
  и email-ветки через тот же `continue`). Классификация:
  - open: `new_task`, `auto_created`
  - status: `status_changed`, `sent_to_review`, `returned_for_rework`,
    `deadline_changed`, `overdue`
  - close: `closed`
  - note: `attachment_added`, `comment_added`, `task_updated`
- **`/profile/notifications`.** Переписан на 2 независимые группы radio:
  «Уведомления по инцидентам» (`name=incident_mode`) и «Уведомления по
  задачам» (`name=task_mode`). Каждый блок с отдельным пояснением. POST
  принимает оба значения, валидирует, сохраняет. Смешение режимов разрешено.

**Распределение после деплоя (367 активных):** по инцидентам 366=all + 1=close_only (user1), по задачам 367=all.

**Откат s60b:**
```
cd /home/user/portal
for f in app/models_legacy.py app/bootstrap.py app/tasks.py app/auth.py \
         app/templates/profile_notifications.html; do
  cp "$f.bak_session60b" "$f"
done
pkill -9 -f 'python3 run.py'; nohup python3 run.py > /tmp/portal.log 2>&1 &
```

## Сессия 60 (24.04.2026) — ЗАДЕПЛОЕНО 24.04.2026

Гибкие уведомления по инцидентам (часть 2 из запроса директора). 6 файлов
(1 новый), `../deploy_session60.py` + `../_s60_restart_smoke.py`, бэкапы
`.bak_session60`, smoke OK.

- **БД.** Новая колонка `"user".notify_incident_mode VARCHAR(20) NOT NULL
  DEFAULT 'all'` (`app/models_legacy.py` + `app/bootstrap.py` ALTER).
  Допустимые значения: `all` / `status` / `open_close` / `close_only`.
- **Фильтрация уведомлений.** В `app/children.py` `_notify_user` добавлен
  параметр `new_status` и блок фильтрации по режиму пользователя. Классы
  событий: `open` (назначение), `status` (промежуточные статусы), `close`
  (resolved + status_change на resolved/closed), `note` (заметки/ответы).
  Матрица проверена unit-тестом `_s60_notify_unit.py`.
- **Страница `/profile/notifications`.** Новый endpoint в `app/auth.py`
  (GET+POST), шаблон `app/templates/profile_notifications.html` — radio-карточки
  с 4 режимами и описаниями. Сохраняется в `current_user.notify_incident_mode`.
- **UI.** В колокольчике `layout.html` рядом с кнопкой «Прочитать» добавлена
  иконка-шестерёнка → `/profile/notifications`.
- **SQL.** `UPDATE "user" SET notify_incident_mode='close_only' WHERE
  username='user1';` — директору (Карпов П.В.) дефолт «только закрытие».
  На проде 366 пользователей с `all`, 1 с `close_only`.

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/models_legacy.py app/bootstrap.py app/children.py app/auth.py \
         app/templates/layout.html; do
  cp "$f.bak_session60" "$f"
done
rm app/templates/profile_notifications.html
pkill -9 -f 'python3 run.py'; nohup python3 run.py > /tmp/portal.log 2>&1 &
# Колонку notify_incident_mode оставить — безопасно.
```

**Отладочный казус:** paramiko PipeTimeout на `nohup &` повторилось (было в s40).
Процесс поднялся, дожали `_s60_restart_smoke.py` (через pgrep + setsid
при необходимости). Unicode-крэш `print('→')` под Windows cp1251 —
запускали с `PYTHONIOENCODING=utf-8`.

## Сессия 59 (24.04.2026) — ЗАДЕПЛОЕНО 24.04.2026

Правки по запросу директора (часть 1 из 2 — гибкие уведомления отложены в сессию 60).
10 файлов, `../deploy_session59.py` + `../_s59_restart_smoke.py`, бэкапы `.bak_session59`,
smoke 8/8 OK.

- **Здание в инцидентах.** В `incidents_registry.html`, `incidents_my.html` и
  таблице «Последние инциденты» на `incidents_dashboard.html` (все вкладки,
  table + list) новая колонка «Здание». В `_build_incident_rows` joinedload
  расширен до `SchoolClass.building`, в kid-dict кладётся
  `building = short_name or name`. В `incidents_dashboard` top_classes теперь
  возвращает 4-tuple `(name, cnt, c_id, building_name)` — в блоке «По классам»
  под названием класса виден корпус через `<span class="text-muted small ms-1">`.
- **Плашка «ШСК · не состоит».** В `child_card.html` перед основным блоком
  спортклуба добавлена короткая серая плашка для учеников, которых нет в
  sportmos-выгрузке или которые не состоят ни в одной команде. С основным
  блоком взаимоисключение через `{% if not (_sc and _sc.in_club) %}`.
- **Значок ⚽ в списке класса.** В `class_detail.html` рядом с ФИО каждого
  ученика иконка `bi-dribbble` (warning, tooltip «Состоит в школьном
  спортивном клубе»). Источник — новый helper `sport_club_in_club(child)`,
  добавленный в `sport_club.py` и экспонированный через
  `core/context_processors.py:inject_sport_club`.
- **Колонка «ШСК N из M» в реестрах.** В `contingent.html` и
  `classes_list.html` между «Макс.» / «Телефон» и «Кубок школы» добавлена
  колонка. Подсчёт в backend через новый `count_in_club_for_children(children)`
  (один проход по sportmos-индексу). Батчи в `contingent` и
  `classes_registry` собирают `children_by_class` через `Child.join(ChildEnrollment)`
  с фильтром по `ended_at IS NULL` + `school_class_id IN (...)`. Кортеж в
  `classes_registry` расширен до 7 элементов — последний `sc_in_club`.

**Важно (feedback_deploy_over_prod):** перед правкой `children.py`,
`contingent.html`, `context_processors.py` синхронизированы с прод-базой —
локальная копия отставала. Бэкап локальных версий: `.bak_s59_local_before_sync`
в `код системы/app/...`.

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/children.py app/sport_club.py app/core/context_processors.py \
         app/templates/incidents_{dashboard,registry,my}.html \
         app/templates/{contingent,classes_list,class_detail,child_card}.html; do
  cp "$f.bak_session59" "$f"
done
pkill -9 -f 'python3 run.py'; nohup python3 run.py > /tmp/portal.log 2>&1 &
```

**Отложено в сессию 60 (запрос директора, часть 2):**
- Гибкие уведомления по инцидентам: новая колонка `User.notify_incident_mode`,
  страница `/profile/notifications` с режимами «на каждое действие / только
  смена статуса / появление и закрытие / только закрытие».
- Директору (username=`user1`, Карпов П.В.) поставить «только закрытие»
  разово SQL-ом; всем остальным дефолт «на каждое действие».

## Сессия 58 (24.04.2026) — ЗАДЕПЛОЕНО 24.04.2026

Три UX-правки по инцидентам и по ШСК. 4 файла, деплой `../deploy_session58.py`,
бэкапы `.bak_session58`, smoke 25/25 OK.

- `app/templates/child_card.html` — из шапки плашки «ШСК · Школьный спортивный
  клуб» убран блок «Виды спорта: …». Sport_type команды в schoolsportmos.ru
  часто расходится с тематикой мероприятия (напр. команда «Новогодний серпантин
  БК» заведена как «Шашки», а ходила на танцы). Теперь в шапке — только
  «Состоит в N командах · M мероприятиях», а вид спорта виден отдельно рядом с
  каждой командой. Плюс короткая подсказка со ссылкой на schoolsportmos.ru и
  оговоркой «вид спорта указан по каждой команде отдельно». Локальный файл был
  за 17 байт от прода (дубль CSS в другом месте) — синхронизирован с прода до
  правки (feedback_deploy_over_prod).
- `app/templates/incident_edit.html` + `app/templates/incidents_my.html` +
  `app/children.py` (endpoint `/incidents/<id>/mark-resolved`) — кнопка
  «Я отработал инцидент» теперь открывает Bootstrap-модалку с обязательным
  описанием работы (`textarea required`) + опциональными вложениями
  (multi-file, те же форматы и лимиты, что в add-note — pdf/doc/xls/jpg/png/
  gif/webp/zip/mp4/mov/webm, 10 файлов, 30/100 МБ). Прежний `prompt()` с
  необязательным комментом — удалён. На сервере `incident_mark_resolved`
  требует непустой `comment` (400 `comment_required` иначе), создаёт
  `IncidentNote(text="[Отработано] …")` и сохраняет прикреплённые файлы через
  существующий `_save_incident_note_attachments()`. В уведомлениях автору и
  ADMIN/DEPUTY — превью коммента, не обрезанное до пустой строки.
- `app/templates/incidents_my.html` + `app/templates/incident_edit.html` +
  `app/children.py` (endpoint `/incidents/<id>/set-assignee` и POST save формы
  карточки) — при назначении исполнителя теперь появляется модалка с
  опциональным «Пояснение для исполнителя». Кнопок две: «Без пояснения» и
  «Назначить с пояснением». Пояснение сохраняется в `IncidentAssignment.note`
  (поле было в БД, но пустовало), дублируется в `IncidentNote("[Назначение] …")`
  и подставляется в уведомление исполнителю вместо описания инцидента. Снятие
  назначения (пустой `assignee_id`) — без модалки, сразу.
  В форме `incident_edit.html` добавлено поле `assignment_note`, показывается,
  только когда assignee выбран.
- `app/templates/incident_new.html` + `app/children.py` (форма `/incidents/new`) —
  новое необязательное поле «Что уже сделано на данный момент» (textarea
  `name="initial_work"` под «Описание»). Если автор его заполнил, после
  создания инцидента backend добавляет `IncidentNote` с префиксом
  `[Сделано автором]` — первая запись журнала работы. Описание инцидента
  остаётся обязательным, проделанная работа — нет.

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/children.py app/templates/child_card.html \
         app/templates/incident_edit.html app/templates/incidents_my.html; do
  cp "$f.bak_session58" "$f"
done
pkill -9 -f 'python3 run.py'; cd /home/user/portal && nohup python3 run.py > /tmp/portal.log 2>&1 &
```

**E2E-проверки на проде (admin):**
- `/children/{9,12,18,103,1}` → 200, шапка «Виды спорта» отсутствует.
- `/incidents/my` → `myMarkResolvedModal` и `setAssigneeModal` на месте.
- `/incidents/60/edit` → `assignmentNoteField` на месте.
- `POST /incidents/60/mark-resolved` без `comment` → 400 `{"error":"comment_required"}`.
- С комментом + вложением локально → IncidentNote `[Отработано] …` + resolved status.
- `POST /incidents/<id>/set-assignee` с `note=...` → IncidentAssignment.note сохранён,
  создан IncidentNote `[Назначение] …`.

## Сессия 56 (24.04.2026) — ЗАДЕПЛОЕНО 24.04.2026

P1 из аудита (после комплексного ревью скорости/уязвимостей/логики). 3 файла,
деплой `../deploy_session56.py`, бэкапы `.bak_session56`, smoke 25/25 OK.

- `app/olympiads.py` — `view_response_cache` TTL 120 с на `/olympiads/`
  (ключ: roles/department_ids + academic_year+stage+subject+teacher+department+status+child_q)
  и на `/olympiads/analytics` (ключ: department_ids + year+teacher+department).
  Замеры на проде (admin, 3 прогона):
  - `/olympiads/` 980 → **353 мс** (−64%) на прогретом кеше
  - `/olympiads/analytics` 1700 → **79 мс** (−95%) на cache hit
- `app/bootstrap.py` — 12 голых `except Exception: pass` заменены на
  `logger.exception()` + rollback. Стартовые ошибки миграции схемы
  (`ensure_runtime_schema`, `seed_olympiad_subject_mappings`) теперь пишутся в лог.
- `app/auth.py` — in-memory rate-limit на `/login`: 5 неудачных попыток
  / 60 с / IP → 5 минут блокировки с HTTP 429. X-Forwarded-For обрабатывается
  (за nginx). Без новых зависимостей. Мёртвый `next_page = request.args.get("next")`
  удалён.

**Откат:** `cp *.bak_session56 *` для `app/auth.py`, `app/bootstrap.py`,
`app/olympiads.py` + рестарт `pkill -9 + nohup python3 run.py`.

Также перед сессией 56 одним коммитом `f823fd7` закоммичены 15 файлов s54+s55
(на проде уже были) + патч SQLite `lower`/`upper` для кириллицы в `core/extensions.py`.

## Сессия 55 (24.04.2026) — ЗАДЕПЛОЕНО 24.04.2026

Фикс по выводам из PageVisit-аналитики (957 просмотров / 15 уников / 44 логина на ролях
за сутки). 3 файла, деплой `../deploy_session55.py`, бэкапы `.bak_session55`, smoke 25/25 OK.

- `app/core/config.py` — `PERMANENT_SESSION_LIFETIME = timedelta(hours=12)`. Раньше не задано
  → сессия «браузерная», умирала при закрытии Chrome, отсюда 44 логина / 15 юзеров.
- `app/auth.py` — `session.permanent = True` перед `login_user(user)`. Теперь кука
  с expires на 12 часов, учитель один раз утром логинится и работает весь день.
- `app/core/page_visit.py` — skip 3xx на GET-запросах. Раньше PageVisit писал оба
  события для `/incidents/dashboard` → 302 → `/incidents/dashboard-legacy`, из-за чего
  в аналитике «два дашборда» с разной популярностью. Редирект-прокси (GET→3xx)
  теперь не логируются. 3xx после POST остаются — там переход информативен.

**Откат:** `cp *.bak_session55 *` для трёх файлов + рестарт `pkill/nohup`.

## Сессия 54 (24.04.2026) — ЗАДЕПЛОЕНО 24.04.2026, коммит `8fd8468`
Плашки «Кубок школы» и «ШСК · Школьный спортивный клуб» в карточке ученика
(`/children/<id>`). Обе сворачиваются/разворачиваются.

**Деплой 24.04.2026:** `../deploy_session54.py`. 3 файла (`app/sport_club.py`,
`app/core/context_processors.py`, `app/templates/child_card.html`) + заливка
`sportmos/full.json` (753 КБ) в `/home/user/portal/sportmos/full.json` +
добавлена строка `SPORTMOS_JSON_PATH=/home/user/portal/sportmos/full.json` в
`.env`. Бэкапы с суффиксом `.bak_session54`. Рестарт через
`pkill -9 + nohup python3 run.py` (pid 374137).

**Merge с прод-базой** (правило feedback_deploy_over_prod): из прода подтянут
`child_card.html` — он содержал мобильный фикс таблицы документов (col-doc-*
классы + @media <768px), которого не было в коммите `8fd8468`. Прод-версия
использована как база, поверх наложены правки s54 через `git merge-file`;
результат 1585 строк. Дубликат CSS-блока, который добавил s54-коммит в начало
файла, удалён — он уже присутствует в оригинальном `<style>` блоке ниже
(прод-вариант).

**На проде:** 3415 детей всего, по ФИО+дате рождения в sportmos матчится 801,
из них 611 состоят в командах. `kubok_rating` работает для 1-9 классов
(нормализация '5ВН' → '5-ВН'). В 10-11 классах имена в нашей БД ('11В')
не совпадают со снэпшотом рейтинга ('11-ВМ'), поэтому для старшеклассников
Кубок-плашка не показывается — это ожидаемое поведение, обсуждено с директором.

**Визуально проверено (admin):** `/children/103` (Галстян Артур, 9ИП) —
Кубок место 30/116, 775 баллов, параллель 1/9, корпус Логика 18/58, 13
активностей; ШСК 3 команды (Мини-футбол/Футбол), 3 мероприятия, источник
schoolsportmos.ru. Смоук 25/25 OK.

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/core/context_processors.py app/templates/child_card.html .env; do
    cp "$f.bak_session54" "$f"
done
rm app/sport_club.py
pkill -9 -f 'python3 run.py'; cd /home/user/portal && nohup python3 run.py > /tmp/portal.log 2>&1 &
```

- `app/sport_club.py` — матчинг Child↔`sportmos/full.json` по meshID + fallback
  (ФИО, `birth_date`). Singleton-кеш по mtime. Возвращает команды (активные первыми,
  свежие сверху), мероприятия (свежие сверху), массив видов спорта.
- `app/core/context_processors.py` — `inject_sport_club` добавляет хелпер
  `sport_club_info(child)` в Jinja-контекст.
- `app/templates/child_card.html`:
  * Кубок — только ADMIN, если `kubok_rating(child.current_class_name)` не None.
    Бейджи «Место: X из Y · N баллов», внутри — диаграмма активностей + бейджи
    «Место в параллели X-х» / «Место в корпусе X».
  * ШСК — всем ролям. «Состоит в N командах · участвовал в M мероприятиях».
    Раскрытие: теги видов спорта, список команд (активные первыми), участие в
    мероприятиях (свежие сверху). Подпись «(свежие сверху)» под разделами.
  * Учебный год поднят в верх перед плашками. Явно указано, что фильтр не влияет
    на Кубок и ШСК — они накопительные.
  * Заголовки плашек нейтральные; яркие акценты — только в раскрытом теле.
  * Олимпиады/Контрольные/Инциденты оставлены на прежних позициях (пробовали
    переносить — директор решил вернуть).

Детали и скриншоты — `../memory/project_session54_sport_club.md`.

## Сессия 53 (23.04.2026) — ЗАДЕПЛОЕНО
UX-фиксы 1/2/5 из плана `project_session53_ux_fixes_plan.md`.
- `layout.html`: в `role_labels` добавлены `SOCIAL_PEDAGOG` и `DEPUTY_DIRECTOR` — шапка перестала показывать голый код роли у SP.
- `children.py` `list_children`: снято ограничение `SchoolClass.teacher_user_id == current_user.id` для CLASS_TEACHER → класс.рук ищет всех. В шаблон передаётся `rows` с per-row флагами `can_view_card` (child-aware через `can_view_child_basic`) и `can_add_incident`.
- `children_list.html`: колонка действий — «+ инцидент» (outline-warning, ведёт на `/incidents/new?student_id=<id>`) для всех с `incident_add`, «Открыть» для тех, кто может открыть карточку конкретного ребёнка.
Итог: TEACHER/CLASS_TEACHER/PSY/SP/ADMIN находят всех учеников и могут создать инцидент; карточка открывается по прежним правилам (class_teacher — только свои, методист — read-only).
Deploy: `../deploy_session53.py`, бэкапы `.bak_session53`. Рестарт `pkill -HUP` положил процесс → поднят через nohup (pid 368248). Полный smoke 25/25 OK. Пункты 3/4 плана (вкладки PSY в /incidents/my, METHODIST-комментарии) отложены.

## Сессия 51 (23.04.2026) — ЗАДЕПЛОЕНО
Оптимизация тяжёлых реестров + дожимка Кубка. 4 файла.

**Перф (цели достигнуты):**
- `/social-passport` — response-кеш TTL 60 с по (roles, year, grade, class_id, q). **1292 → 45 мс (−96%)**, цель <400.
- `/classes` — response-кеш TTL 60 с по (year_id, q). Инвалидация на CRUD (update/create/delete/copy-from-year). **671 → 39 мс (−94%)**, цель <200.
- `/contingent` — Python-цикл по 2000 детям заменён на SQL GROUP BY (boys/girls/ovz/vshu/kdn/education_form). Убрал загрузку всех Child+social. **392 → 123 мс (−69%)**, цель <200.

**Кеш:** новый `view_response_cache` (`app/core/cache.py`), `TTLCache(max_entries=16)` с LRU-eviction. Защита от OOM при больших HTML.

**Кубок:** `_load_snapshots_by_name` теперь через join с SchoolClass обогащает rating полями `place_in_parallel`, `total_in_parallel`, `place_in_building`, `total_in_building`, `grade`, `building_name`. На странице класса (`/classes/<id>`) выводятся бейджи «7-е классы: #2 из 9», «Корпус А: #3 из 42» под основным местом.

Бэкапы `.bak_perf_s51` на проде. Смоук 25/25 OK. Deploy `../deploy_perf_session51.py`.

## Сессия 50 (23.04.2026) — ЗАДЕПЛОЕНО
Оптимизация подстраниц раздела «Обучающиеся». 3 точечных правки в `app/children.py`:
- `registry_enrolled` — `contains_eager(child, school_class)` убрал N+1 на 3388 enrollments. **5621 мс → 444 мс (−92%)**.
- `_build_incident_rows` — `joinedload(Child.enrollments→school_class)` убрал N+1 на `ch.current_class_name`.
- `incidents_registry` — `joinedload(Incident.author, assignee)` убрал N+1 на author_label/assignee в шаблоне. **334 мс → 122 мс (−63%)**.

Бэкап `.bak_perf_s50` на проде. Шаблоны не трогали. Полный smoke 25/25 OK. Deploy-скрипт `../deploy_perf_session50.py`.

## Сессия 49 (23.04.2026) — ЗАДЕПЛОЕНО, коммит `edf805b`
Техдолг и чистки: SP-инструкции в БЗ (ids 13-15), Task→Incident sync в `tasks.py`, legacy-редиректы `/users` / `/analytics/dashboard` / `/settings/organization`, `/orders/` починен через strict_slashes=False, ежедневный retention `page_visit` 30 дней (04:10 МСК), плитка «Добавить ученика» в темах «Основные реестры» и «Контингент». 5 python-файлов + 3 HTML. Бэкапы `.bak_session49`. Детали — `../memory/project_session49_maintenance.md`.

Отложено на отдельные сессии: оптимизация `/social-passport` 1.4s, `/classes` 0.6-0.9s, `/contingent` 0.3-0.5s; доработка Кубка (разрез параллели, визуал).

## Сессия 47 (23.04.2026) — ЗАДЕПЛОЕНО
PageVisit-журнал + страница `/admin/users/paths` (топ-страниц, переходов, лента юзера). 4 модифицированных + 3 новых файла. Таблица создаётся через `db.create_all()`. Деталей — `../memory/project_session47_page_visit.md`. Retention/named events отложены, мониторить рост таблицы.

## ⚠️ Перед деплоем — прочитать `../memory/project_session42_incidents_tasks_rework.md`

Сессия 42 (22.04.2026) — большая переработка инцидентов и задач. **Локально, НЕ задеплоена.**
15 изменённых + 1 новый файл на ветке `feature/kubok-school`, не закоммичено.

Кратко:
- Колокольчик с фильтром «Все/Инциденты/Задачи» через иконку-воронку
- Плитка «Инциденты» для ADMIN/DEPUTY на главной (вместо «Мои заявки»)
- `/incidents/my` admin-view: 3 вкладки (Входящие/В работе/Завершённые) + фильтры + живой поиск + picker assignee прямо в строке
- `/incidents/my` user-view: 2 вкладки (Мои заявки / Назначены мне) с кнопкой «Я отработал»
- METHODIST получил read-only доступ к карточке инцидента
- Разделены `_can_view_incident` / `_can_edit_incident` / `_can_change_status`
- SQLite unicode LOWER в `app/core/extensions.py` (критично — без него поиск по кириллице не работает)
- Секция «Связанные задачи» в карточке инцидента + плашка «Задача из инцидента» в карточке задачи
- `tasks/list.html`: свёрнутые показатели/фильтры, убраны дубли, сайдбар в 3 блока
- 3 инструкции для ADMIN в /knowledge/ + 11 скринов

Ничего миграций-критичных не нужно — таблицы из s41 (`incident_assignment`, `incident_status_history`,
`incident_notification`, `task.incident_id`) создаются через `db.create_all()` + bootstrap.py на проде
при первом запуске. Записи в `knowledge_article` для ADMIN (3 строки) — добавить INSERT'ом как в s35.

## Стек и запуск

- Python 3, Flask, SQLAlchemy, PostgreSQL (prod) / SQLite (local)
- Точка входа: `run.py`
- Локально: `python run.py` (SQLite, порт 5001)
- **Никогда не запускай** `flask run` напрямую — только через `run.py`

## Структура

```
run.py / app/__init__.py / app/config.py / app/extensions.py
app/models_legacy.py      → ГЛАВНЫЙ файл моделей (1274 строк)
app/permissions.py        → матрица прав: has_permission(), has_role(), is_admin()
app/children.py           → дети, инциденты, соц.паспорт, contingent, roles_admin
app/modules/hub/routes.py → главная страница, фильтрация секций по ролям
app/core/context_processors.py → уведомления + авто-хлебные крошки (100+ эндпоинтов)
app/role_access_admin.py  → настройка доступа по ролям (/admin/role-access)
app/departments.py        → кафедры
app/tasks.py / app/modules/tasks/ → задачи и поручения
app/templates/            → Jinja2 HTML
app/static/css/app.css    → стили
```

## База данных

- Локально: SQLite (`app.db` в корне)
- Продакшн: PostgreSQL, строка подключения в `DATABASE_URL`
- Инициализация: `flask --app run init-db` → `flask --app run repair-runtime-columns`
- **Никогда не запускай** миграции без явного согласования — пользователь применяет сам на сервере

## Роли

`ADMIN`, `CLASS_TEACHER`, `TEACHER`, `PSYCHOLOGIST`, `SOCIAL_PEDAGOG`, `METHODIST`, `KPP`, `VIEWER`, `DEPUTY_DIRECTOR`

**Важно:** двойная схема — `user.role` (старое) + `user_role` many-to-many (новое).
`_user_role_codes()` предпочитает `user.roles`, fallback на `user.role`.
При проверках прав — только через `is_admin()`, `has_role()` из `permissions.py`, не `user.role` напрямую.

## Деплой

- Сервер: `10.174.241.7:22`, user / RTYq
- Путь: `/home/user/portal`
- `.env` на сервере: `DATABASE_URL=postgresql://school_user:StrongPassword123!@localhost/school_portal`
- Деплой через paramiko (SSH + SFTP): загружаем файлы → сервис перезапускается сам (debug + file watcher)
- Бэкапы перед заливкой: суффикс `.bak_<задача>`
- **Деплой только при школьном WiFi**

## Локальный запуск

- `python run.py` → сервер на порту 5001
- Нужен учебный год: `AcademicYear(name='2025/2026', is_current=True)` — иначе дашборд падает
- Админ: `python init_admin.py` → логин `admin` / `admin123`
- `weasyprint` не работает на Windows без GTK — PDF недоступен локально (обёрнут в try/except)

**Тестовые пользователи (SQLite):**

| Логин | Пароль | Роль |
|-------|--------|------|
| admin | admin123 | ADMIN |
| test_class_teacher | test123 | CLASS_TEACHER |
| test_psychologist | test123 | PSYCHOLOGIST |
| test_social | test123 | SOCIAL_PEDAGOG |
| test_teacher | test123 | TEACHER |
| KPP | 123 | KPP |

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

## Текущий статус (13.04.2026, сессия 20 — CLASS_TEACHER роли)

**Все правки до сессии 29 включительно — ЗАДЕПЛОЕНЫ.** Система работает на `http://10.174.241.7/` (порт 5001, nginx проксирует).

**Что сделано в сессии 18:**
- SOCIAL_PEDAGOG получил полный доступ ко всем разделам (МЦКО, олимпиады, контрольные, соц.паспорт, посещаемость)
- `permissions.py`: +7 permissions, `role_access_admin.py`: MODULE_DEFAULT_ROLES
- `children.py`: social_passport_dashboard для METHODIST+SOCIAL_PEDAGOG, subqueryload N+1 fix
- `social_passport_registry.html`: `ch.social.X` вместо `ch.X` (поля были всегда «—»)
- `hub/routes.py`: «Инциденты класса» + «Пропуски класса» — roles_any с SOCIAL_PEDAGOG
- `attendance.py`: analytics/passes/issue_pass через `has_any_role` с SOCIAL_PEDAGOG
- `diagnostics.py`: `_is_social_pedagog()`, manage/import/visibility/binding
- Деплой: `deploy_social_pedagog_full.py`, git `0f1c266`

**Что сделано в сессии 16:**
- Баг: `users.py` использовал код `SOCIAL_PEDAGOGUE` (с E), а `permissions.py` и `hub/routes.py` — `SOCIAL_PEDAGOG` (без E). Из-за этого `has_role("SOCIAL_PEDAGOG")` возвращал False при смене роли через `/admin/users/edit`. Шапка показывала правильный лейбл, но разделы не открывались.
- Исправлено в `users.py`: ROLE_OPTIONS, ROLE_LABELS, RUSSIAN_ROLE_MAP, SERVICE_ROLE_CODES — везде `SOCIAL_PEDAGOGUE` → `SOCIAL_PEDAGOG`
- `hub/routes.py`: добавлен SOCIAL_PEDAGOG в "Управленческий контур" (tile + theme config) — теперь SOCIAL_PEDAGOG видит все блоки кроме "Служебные действия / Для администратора"
- `children.py`: убран дубль `SOCIAL_PEDAGOGUE` из `_ROLE_PRIORITY`
- SQL: назначены роли Баталиной Елене, Коновал Софии Гришаевне + синхронизированы 2 пользователя у которых был неверный код
- Деплой: `deploy_social_pedagog_users.py`

**Что сделано в сессии 15:**
- Расширены права SOCIAL_PEDAGOG: блоки 1+2 главной как у ADMIN, без 3-й административной панели
- `permissions.py`: +incident_registry_view, +control_works_view, +olympiad_view, +olympiad_dashboard_view, +social_passport_registry_view, +social_passport_dashboard_view
- `hub/routes.py`: SOCIAL_PEDAGOG добавлен в roles_any для Пропуска/Приказы/Классное руководство/План работы (tiles + theme pages)
- `role_access_admin.py`: MODULE_DEFAULT_ROLES обновлён — страница /admin/role-access корректно отображает настройки SOCIAL_PEDAGOG
- Деплой: `deploy_social_pedagog_fix.py` + `deploy_social_pedagog_fix2.py`

**Что сделано в сессии 14:**
- Баг: смена роли через `/admin/users/edit` не применялась — форма писала только `user.role`, но `_user_role_codes()` смотрит сначала `user.roles` (many-to-many), которая не обновлялась
- Добавлена `_sync_user_roles_table()` в `app/users.py` — синхронизирует `user_role` при каждом сохранении
- Задеплоен `deploy_role_fix.py`, commit `c010579`

**Что сделано в сессии 11:**
- Hotfix: `search_children_ajax` (children.py:615) — loop-распаковка `(child, cls, enrollment)` → `child` + `child.current_class_name`
- Hotfix: Enter в поиске на главной (dashboard.html) — теперь редиректит на `/children?q=...`
- Деплой через патч конкретных строк (SFTP), не замена файла целиком

**Что сделано в сессии 10:**
- Деплой правок 8–21 (25 файлов + 4 SQL-миграции)
- Исправлен баг: `app/modules/__init__.py` содержал `from .dev import dev_bp` → убрано
- Cache-busting: `app.css?v=20260413` в layout.html
- Дашборд инцидентов: user_activity фильтруется по class_id/grade/category
- Заголовки чартов: «По категориям», «По зданиям», «По классам», «По статусу»

**`app/modules/dev.py` — НЕ деплоить** (только для локального DEBUG, модуль отсутствует на сервере)

**Что сделано в сессии 20:**
- КРИТИЧЕСКИЙ БАГ: все 116 кл. руководителей имели роль TEACHER вместо CLASS_TEACHER
- Из-за этого не работали: "Мой класс", соц. паспорта, ограничение классом, реестры, пропуска
- SQL: обновлены user.role + user_role для всех 116 привязанных к классам (113 TEACHER + 2 VIEWER + 1 ADMIN)
- Деплой: `deploy_class_teacher_role.py`, только SQL, код не менялся
- Кафедры решено оставить видимыми для всех ролей (по решению пользователя)

**match_class_teachers.py — не нужен:** все 116 классов имеют teacher_user_id, роли CLASS_TEACHER назначены.

**Что сделано в сессии 21 (perf) — ЗАДЕПЛОЕНО 13.04.2026:**
- Оптимизация скорости: 10 исправлений N+1, batch-запросы, GROUP BY, DB-пагинация
- Новый profiler middleware: `app/core/profiler.py` — логирует время + SQL на каждый запрос
- children.py: _build_incident_rows batch, daily/status GROUP BY, social_passport_dashboard переписан, list_children DB pagination
- models_legacy.py: кеш AcademicYear в current_enrollment
- service_staff.py, control_works.py, olympiads.py: eager loading / batch / cache
- git: `1a2e2d9`, деплой: `deploy_performance.py` (7 файлов, smoke 8/8 OK)

**Сессия 22 — аудит скорости после деплоя perf:**
- Полный аудит 26 страниц под авторизованной сессией (admin/admin123)
- Дашборд инцидентов: 42ms (было тысячи), social_passport_dashboard: 103ms
- Оставшиеся медленные: `/olympiads/analytics` 1.7s, `/social-passport` 1.3s, `/olympiads/` 980ms, `/` 546ms

**Сессия 23 — оптимизация 4 медленных страниц (ЗАКОММИЧЕНА, НЕ ЗАДЕПЛОЕНА):**
- git: `5e542e1`, деплой: `deploy_perf_pages.py` (4 файла, smoke 8 URL)
- `olympiad_stats_service.py`: `all_analytics()` — 1 загрузка вместо 6, yearly_comparison через GROUP BY
- `olympiads.py`: joinedload child/teacher/subject/school_class/department в registry
- `children.py`: joinedload вместо subqueryload для Child.social (1:1) в social-passport
- `main.py`: SQL COUNT/AVG/GROUP BY в 4 dashboard-функциях вместо .all() в Python

**Что сделано в сессии 25 (P0+P2 аудит) — ЗАДЕПЛОЕНО 13.04.2026:**
- P0 #1: CSRF-защита — Flask-WTF CSRFProtect + авто-инъекция токенов (мета-тег + JS) во все формы и fetch
- P0 #2: `require_roles` переписан на `has_any_role()` из permissions.py
- P2 #9: Гамбургер-меню для мобильных (navbar-toggler + collapse + CSS)
- P2 #10: Cookie безопасности (HttpOnly, SameSite=Lax)
- git: `43966d9`, деплой: `deploy_p0_p2_audit.py` (9 файлов, smoke 6/6 OK)

**Что сделано в сессии 26 (UI v110 → master) — ЗАДЕПЛОЕНО 15.04.2026:**
- git: `1427221`
- `incidents_dashboard.html`: col-picker fix, stats-strip 3 цифры чёрные, «По статусу» без rank-rows, активность топ-5 + expand, иконки карандаш/корзина
- `incidents_registry.html`: hero + фильтр в стиле дашборда, col-picker, view-switcher table/list, иконки

**Что сделано в сессии 27 — ЗАДЕПЛОЕНО 15.04.2026:**
- git: `09be80a`
- Убраны подписи под hero-заголовками (дашборд + реестр)
- Кнопки Применить/Сброс: `btn-sm + col-auto`
- List-view: кнопка корзина рядом с карандашом
- Категории: убран оранжевый пилл → plain black text
- Статусы badge: Notion-style dot ::before
- Col-picker: Bootstrap → custom JS toggle

**Что сделано в сессии 28 — ЗАДЕПЛОЕНО 15.04.2026:**
- git: `6189784`
- Кнопки реестра: Дашборд | Excel | На главную (зеркально дашборду)
- Notion-style пикер статусов (кастомный dropdown, белое окошко с группами)
- Col-picker: теперь работает и в list view (добавлены col-* классы к элементам списка)

**Что сделано в сессии 29 — ЗАДЕПЛОЕНО 15.04.2026:**
- git: `6189784` + bugfix
- Сверка локальных файлов с серверными (children.py, 2 шаблона) — ОК, ничего не потеряно
- **Bugfix**: AJAX status picker path `/children/incidents/` → `/incidents/` (blueprint без url_prefix)
- Деплой: `deploy_v110_ui.py` (3 файла: children.py + 2 шаблона, бэкапы `.bak_v110_ui`)
- Данные инцидентов не затронуты (только UI + 3 строки status_filter в бэкенде)

**Что сделано в сессии 30 — ЗАДЕПЛОЕНО 15.04.2026:**
- git: `08cf2ca`
- Описание инцидента в табличном виде (дашборд + реестр): truncate до 60 символов + кнопка ▸/▾ развернуть/свернуть
- List view без изменений
- Деплой: `deploy_desc_truncate.py` (2 шаблона, бэкапы `.bak_desc_truncate`)

**Сессия 32 — ОТКАЧЕНА 20.04.2026 (вечер), кеш сохранён**

Пользователь не давал согласия на чистку навигации («просил не трогать главную,
только оптимизация»). Откат коммитом `5701b11` — hub/routes.py, permissions.py
и dashboard.html возвращены к состоянию `0f1c266`. Кеш `_summary_cards` (TTL 60с)
из `de94eac` сохранён и работает поверх старой навигации.

Что восстановлено:
- Темы `/hub/contingent`, `/hub/registries`, `/hub/management`, `/hub/academic`,
  `/hub/control-works` — снова отдают 200 и содержат свои плитки.
- Плитки «Движение» / «Движение контингента» (→ `transfers.index`) — снова в
  темах `registries` и `contingent`. Модуль `transfers/` остался на сервере.
- Плитка «Основные реестры» (→ /hub/registries) + «Контрольные работы»
  (→ /hub/control-works) — снова на главной.
- Плитка «Инциденты» показывается всем ролям (убрано скрытие у classroom-ролей).
- Плитка «Мои заявки» в dashboard ролика — откачена (была добавлена в 086678e).

Deploy отката: `../deploy_revert_session32_nav.py`, бэкапы `.bak_revert_s32`.
Smoke 25/25 OK, главная 139–202ms, кеш работает.

**Исходная сессия 32 (для истории):**
Пересмотрен аудит 15.04. Откладываем техдолг на лето. 3 коммита:
- `746a67d` feat(hub): чистка навигации — убраны 2 дубля theme_configs
  (registries≡contingent, control_works≡academic), удалены 5 orphan routes
  (management/academic/contingent/registries/control-works), плитка «Инциденты»
  добавлена на главную → раскрывает category-фильтры (Травмы/Драки/Буллинг/Дисциплина).
  +PSYCHOLOGIST в `incident_registry_view` (видит все 7 карточек в /hub/incidents).
- `086678e` feat(dashboard): +5-я плитка «Мои заявки» у классрука после «Мои задачи».
  Плитка «Инциденты» в secondary_sections скрыта у ролей без реестра/дашборда
  (CLASS_TEACHER/TEACHER не видят — у них уже есть «Добавить инцидент» и «Мои заявки»).
- `de94eac` perf(hub): кеш `_summary_cards()` на 60 секунд. Локально
  главная 546ms → 37ms (холодный кеш — 129ms, тёплый — 29-45ms).
Деплой: `deploy_hub_cleanup.py` + `deploy_class_teacher_dashboard.py`.
После деплоя smoke_test 25/25 OK, 5 удалённых routes → 404, /hub/incidents = 7 карточек.
Бэкапы на сервере: `*.bak_hub_cleanup`, `dashboard.html.bak_class_teacher_dashboard`.
Локальный бэкап серверного состояния до деплоя: `incident_547/server_backup/pre_session32/`.

**Попутно починено при деплое 20.04.2026:**
- `smoke_test.py`: добавлен CSRF-токен в POST /login — раньше падал с HTTP 400
  (Flask-WTF блокировал логин). Шаблон: GET /login → вытащить `csrf_token` → POST.
- Пароль admin на сервере: **admin123** (в deploy-скриптах был старый SchoolAdmin547!
  — там login возвращал 400, но 404/302-проверки всё равно сработали).

**Что сделано в сессии 33 (17–18.04.2026) — НЕ ЗАКОММИЧЕНО, НЕ ЗАДЕПЛОЕНО.
На 20.04.2026 решено: скорее всего делать не будем, оставляем как есть.**
Реализованы P1-1 шаги 8–9 из аудита сессии 31 (главная — сокращение до 8 блоков).
Затронуты 2 файла: `app/modules/hub/routes.py` + `app/templates/contingent.html`.

Secondary_sections: 11 блоков → 8. Удалено: «Задачи и поручения» (дубль с
quick_action «Мои задачи»), «Соц-психологическая служба» (→ внутрь theme
`classroom` как карточка «Специалисты службы»), «План работы школы» + «База
знаний» (→ объединены в новый theme `reference`).

Новый theme `reference` (план школы + база знаний), новый route `/hub/reference`.

Theme `classroom` переименован в «Сопровождение учеников», +PSYCHOLOGIST в roles_any,
+карточка «Специалисты службы» (`service_staff.index`, доступ ADMIN/METHODIST/
PSYCHOLOGIST/SOCIAL_PEDAGOG).

Contingent: добавлены 3 плашки АЗ/Зачисленные/Отчисленные рядом с ОВЗ/ВШУ/КДН —
восстановлен доступ к orphan endpoints `registry_az`/`registry_enrolled`/
`registry_expelled` (раньше имели код/view/template, но 0 навигационных ссылок).

Локально протестировано под admin / test_class_teacher / test_teacher /
test_psychologist / test_social (все HTTP-коды ожидаемые, карточки theme
корректно фильтруются по roles/permissions).

Копия для сверки: `incident_547/versions/session33_nav_v1/` —
before/ (оригиналы) + after/ (результат) + CHANGES.md с smoke-таблицей.

Замечено: `core_bp` в `app/core.py` содержит endpoint `movements_registry`,
но сам blueprint нигде не регистрируется в `register_blueprints()`. Endpoint
фантомный. Решать в будущем (зарегистрировать или удалить).

**Что сделано в сессии 34 (20.04.2026) — ЗАДЕПЛОЕНО 20.04.2026:**
Инструкции для 3 ролей встроены в существующий раздел «База знаний» (`/knowledge/`).
- 9 HTML-инструкций (TEACHER/CLASS_TEACHER/PSYCHOLOGIST × старт/инцидент/класс)
  — мастер-копия в `incident_547/инструкции/` (HTML + `_images/` + `style.css` +
  `index.html` для standalone-просмотра). Скриншоты сняты под реальными ролями
  через Playwright.
- Копия для раздачи Flask: `код системы/app/static/guides/` → добавлена в
  `.git/info/exclude` (локально, не в коммите).
- `app/templates/knowledge_article.html`: если `article.link` начинается с
  `/static/guides/` → рендерим `<iframe height=85vh>`, иначе старая плашка.
  Badge «Инструкция» (вместо «Ссылка») для наших.
- `app/templates/knowledge_list.html`: иконка `bi-book` и badge «Инструкция»
  для наших статей; старое поведение для реальных внешних ссылок сохранено.
- БД `instance/app.db` (SQLite, локально): 3 тестовые статьи удалены,
  9 новых вставлены (`kind='link'`, `link='/static/guides/...'`,
  `target_roles=["ROLE"]`, `is_published=1`, `sort_order` 10..90).

**Деплой в сессии 35 (20.04.2026):**
- Скрипт: `../deploy_session34_guides.py` (paramiko).
- Залиты 2 шаблона (бэкапы `.bak_session34_guides`) + 29 файлов в
  `/home/user/portal/app/static/guides/` (9 HTML + style.css + 19 PNG).
- `index.html` из `guides/` НЕ заливался — это standalone-навигация,
  в системе дублирует `/knowledge/` (умышленный пропуск).
- На проде таблица `knowledge_article` была пустой (0 строк) — DELETE не нужен,
  только INSERT 9 новых (IDs 1–9, sort_order 10..90).
- Smoke: `/knowledge/` 36ms, статья с iframe 25–46ms, Cyrillic-статика 17ms.
  Полный `smoke_test.py` — 25/25 OK, регрессий нет.
- Откат: `cp <file>.bak_session34_guides <file>` + `TRUNCATE knowledge_article`.
- `app/static/guides/` по-прежнему в `.git/info/exclude` (не коммитим).

**Session 33 в сессии 34 засунута в `git stash`** ("session33_nav_v1 uncommitted (отложено)")
чтобы локалка совпадала с серверным состоянием после сессии 32. Вернуть: `git stash pop`.

**Что сделано в сессии 40 (21.04.2026) — ЗАДЕПЛОЕНО 21.04.2026:**
Мониторинг активности пользователей для ADMIN. Коммит `d7fd1b8` на `feature/kubok-school`.

- `User.last_seen_at` + `User.active_days_count` — 2 новые колонки.
- `app/core/activity.py` — `before_request` handler. На любом HTTP-запросе
  авторизованного юзера делает один `UPDATE "user" ...` с троттлингом 1 час
  через SQL-условие (не в Python) + инкрементом `active_days_count` при
  пересечении календарной даты. Skip для static/анонимных, try/except/rollback.
- `/admin/users/activity` (ADMIN only, `app/users.py`) — 5 корзин-карточек
  сверху (всего / активные за 7 дней / 8–30 / > 30 / никогда), кликабельные
  как фильтр. Сортировка 5 вариантов. Подсветка «никогда» розовым, «давно» бледно-оранжевым.
- Плитка «Активность пользователей» в `admin_sections` главной (иконка
  `bi-activity`). Блок «Для администратора» скрывается у не-админов через
  `show_admin_block`. Декоратор `@require_roles("ADMIN")` закрывает роут от прямого URL.
- `bootstrap.py`: +3 ALTER TABLE (`last_login_at`/`last_seen_at`/`active_days_count`)
  в блок `"user"`, идемпотентно.

Deploy: `../deploy_user_activity.py` — 7 файлов (5 изменённых + 2 новых),
бэкапы `.bak_activity20260421`, 2 `ALTER TABLE ... IF NOT EXISTS`, рестарт
процесса. SSH deploy-скрипт подвис на `nohup ... & disown` (paramiko
PipeTimeout), Flask запустился нормально (pid 336010, debug=off, порт 5001).
Smoke отдельно: 12/12 OK, `/admin/users/activity` 77ms.

**На проде после деплоя:** 363 активных сотрудника, 7 заходивших за 7 дней
(с вечера 20.04 — когда задеплоили `last_login_at` в с.39), 356 «никогда»
(нормально — `last_login_at` пишется только со вчера, теперь заполнится).

Откат: `cp *.bak_activity20260421` + `rm activity.py users_activity.html` +
рестарт. Колонки БД оставить — безопасно.

См. `../memory/project_session40_user_activity.md` — детали и откат.

---

**Что сделано в сессии 39 (21.04.2026) — ЗАДЕПЛОЕНО 21.04.2026:**
Срочные правки по полному аудиту системы. Коммит `65bc689` на `feature/kubok-school`.

10 правок кода + 4 SQL-миграции + ротация секретов:
- `child_events.from_class/to_class` VARCHAR(20)→200, promotion_kind 20→30 —
  отчисление/перевод в учреждение с длинным названием больше не валит 500.
- `tasks.py` edit_task: передаётся `template_defaults={}, selected_template=None` —
  `GET /tasks/<id>/edit` больше не валит 500 с jinja `UndefinedError`.
- `run.py`: debug теперь через `FLASK_DEBUG` env — на проде `debug=off`,
  Werkzeug debugger с консолью больше не светится пользователям.
- `config.py`: +SESSION_COOKIE_HTTPONLY/SAMESITE/SECURE (SECURE через env,
  пока False — сайт на HTTP:80). Remember-cookie те же настройки.
- `__init__.py`: KPP больше не создаётся с хардкод-паролем `"123"`, берётся
  из `KPP_INITIAL_PASSWORD` env или `secrets.token_urlsafe(12)`.
- `children.py:1469`: `is_admin(current_user)` вместо `user.role == "ADMIN"`.
- `children.py:4454`: явный case для CLASS_TEACHER (раньше user.role
  оставался старым если выбран только CT).
- `User.last_login_at` — новая колонка + запись в `auth.py` при логине.
- `main.py._dashboard_stats`: `.scalar_subquery()` — 4 SAWarning ушли.
- `iom/form.html` + `iom.py:2083`: `|safe` → `|tojson` (+передаём объект).

Секреты на сервере:
- **SECRET_KEY** ротирован (`secrets.token_urlsafe(64)` в `.env`) — все
  действующие сессии при рестарте стали невалидными, пользователи
  перелогинились. Старый дефолт `change_me_very_long_random_string` был
  в примерах документации и позволял подделать сессию.
- **Пароль KPP** ротирован в БД. Новое значение передано пользователю
  для раздачи вахте.

Системное:
- Прибит старый процесс `python3 run.py` (pid 259203 с 13.04), запущен
  один новый (pid 333890). Порт 5001 слушает один PID. `Debug mode: off`
  подтверждено в логах.
- Найдено 0 `.bak` файлов старше 14 дней. После деплоя на сервере
  137 `.bak` (включая наши 10 `.bak_fix20260421` + `.env.bak_fix20260421`).

Deploy: `../deploy_fix_urgent_20260421.py`, smoke 25/25 OK.
`GET /tasks/2/edit` → 200 (было 500). `last_login_at` пишется (проверено).

Откат: `cp <file>.bak_fix20260421 <file>` для всех 10 файлов + `.env`,
затем `pkill -f 'python3 run.py' && nohup python3 run.py > /tmp/portal.log 2>&1 &`.
ALTER TABLE и колонку `last_login_at` в БД оставить — безопасно.

**Что намеренно не трогали:**
- `SESSION_COOKIE_SECURE=True` — пока HTTP:80, True сломает куки. Ждём HTTPS осенью.
- StrictUndefined в Jinja — слишком широкое, может поломать случайные шаблоны.
- `document_preview.html |safe` — нужен отдельный обзор генерации preview_html.
- Werkzeug dev-server warning — production WSGI (gunicorn) оставлен на осень.

См. `../memory/project_session39_urgent_fixes.md` — подробности и откат.

---

**Что сделано в сессии 36 (20.04.2026) — ЛОКАЛЬНО, НЕ ЗАКОММИЧЕНО, НЕ ЗАДЕПЛОЕНО.
Ждёт доработок, потом деплой.**

Интеграция «Кубок школы» (рейтинг класса) в карточку ученика и отдельную
страницу класса. Пробовали DataLens через JWT-iframe — упёрлись в 403/убогий
вид; перешли на локальное вычисление из открытой Google Sheets.

- Новые файлы: `app/kubok.py` (download xlsx → aggregate → cache),
  `app/models/kubok.py` (модель `ClassRatingSnapshot`),
  `app/templates/datalens_class.html` (нативная страница рейтинга),
  `seed_real_classes.py` (только локальный seed — 6 реальных классов
  7-ПМ/7-НИ/4-ВН/11-ВМ/10-ГА/6-АГ + 7 тестовых детей).
- Изменены: `app/datalens.py` (route `/datalens/class/<id>` теперь отдаёт
  нативные данные, не iframe), `app/core/context_processors.py`
  (helper `kubok_rating`), `app/cli/commands.py` (+`refresh-kubok`),
  `app/models/__init__.py`, `app/modules/__init__.py` (+`datalens_bp`),
  `app/templates/child_card.html` (после шапки — карточка Кубка с
  местом/баллами/активностями), `app/templates/classes_list.html`
  (кнопка «Кубок» в строке класса), `requirements.txt` (+PyJWT, cryptography).
- Локальная конфигурация: `.env` с `KUBOK_SHEET_ID`, `KUBOK_YEAR_LABEL`,
  `DATALENS_DASHBOARD_URL` (последний — только для кнопки «Полный дашборд»).
  `instance/datalens_private_key.pem` лежит в gitignored `instance/`.
- Источник: открытая Google Sheets `1GMCuc_4v0tbXG6f_OIg0MXB1rAV__maqBtZ4UJ7hUTI`
  (листы «Журнал рейтинга», «Список классов», «Все даты»). Агрегация:
  SUM(баллы) GROUP BY класс → rank по всей школе (116 классов).
  Ленивое обновление кеша (> 24 ч → refresh при первом запросе) или
  вручную: `python -m flask --app run refresh-kubok`.
- Подтверждено совпадение с DataLens: 7-НИ место 1 (1490), 4-ВН место 4 (1315),
  7-ПМ место 27 (825), 11-ВМ место 113 (115).
- Ждёт доработок: автообновление по расписанию, права доступа по ролям,
  возможно разрез по параллели/зданию, косметика UI. Детали:
  `../memory/project_session36_datalens.md`.
- На сервере после деплоя: автосоздание таблицы `class_rating_snapshot` через
  `db.create_all()` (проверить на PG), первый `refresh-kubok`, доступ
  сервера к docs.google.com.

**Ближайшие задачи (следующая сессия):**
- Сессия 33 — пока не трогаем, с большой вероятностью не будем делать.
  Правки в stash + `versions/session33_nav_v1/`; решение отложено.
- Весь техдолг (декомпозиция children.py, except/print/Query.get, JS/CSS) —
  отложен на лето/осенний перенос сервера (решение сессии 32).

Подробная очередь: `../memory/project_pending_fixes.md`
Дорожная карта: `../ROADMAP.md`

## Правила работы

- git в `код системы/` — источник правды. "Обновление от 6 апреля" — устарело, не брать.
- В конце сессии: остановить сервер, обновить память, git commit.
- Историю изменений см. в `git log --oneline`.
