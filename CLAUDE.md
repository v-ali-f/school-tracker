# school-tracker — школа №547

Внутренняя система. Flask + PostgreSQL. В эксплуатации, логины розданы 31.03.2026.

## Сессия 96 (28.04.2026) — Множественные исполнители инцидента — ЗАДЕПЛОЕНО

Запрос директора: один инцидент → несколько исполнителей (драка между классами,
оба класс.рука должны видеть и работать). 6 файлов, новая таблица
`incident_assignee` (M2M) + индекс + автобэкфилл — всё через `bootstrap.py`.

**Решения по UX (с пользователем):**
- Уведомления (статус/комменты) — всем назначенным.
- Авто-Task — каждому PSY/SOC/METHODIST своя (могут обсуждать общую).
- Email — не трогаем (по умолчанию off).

**Изменения:**
- `Incident.assignees` (M2M через `incident_assignee`), `assignee_id` остаётся
  как «основной» (последний добавленный) для обратной совместимости.
- `_apply_assignees_change(inc, new_ids, note)` — diff added/removed,
  IncidentAssignment row на каждое изменение, IncidentNote `[Назначение]`,
  авто-статус new↔assigned, _auto_create_task_for_incident на каждого added.
- Все права (`_can_view/edit/mark_resolved`, add_note, timeline) — через
  `_uid_is_assignee` (любой из assignees).
- SQL-фильтры (`?assignee=me`, social-view, kanban, /my user) — через
  `Incident.assignees.any(id=uid)`.
- Уведомления о смене статуса/заметках — всем assignees, дедуп через `set()`.
- Endpoints `/set-assignee` и `/edit` принимают `assignee_ids[]`.
- `_build_incident_rows` отдаёт `r.assignee_ids` + `r.assignees_label` в
  шаблон, `selectinload(Incident.assignees)` для N+1.

**UI:**
- `incident_edit.html` — dropdown picker «Исполнители» (form-select chips +
  раскрывающийся список с чекбоксами + поиск, click-outside закрывает).
- `incidents_my.html` (table/list/kanban) — picker «Назначить» переделан на
  multi-select (чекбоксы + поиск + «Применить»/«Очистить»). При новых
  добавлениях — модалка `setAssigneeModal` с опциональным «Пояснением».
  Все условия `r.inc.assignee_id == current_user_id` →
  `current_user_id in r.assignee_ids`.
- `incidents_registry.html` — колонка `r.assignees_label` + METHODIST gate.

**SQLAlchemy ловушка:** в `IncidentAssignee` две FK на user (`user_id` и
`added_by_id`) — relationship `assignees` с `secondary` требует явных
`primaryjoin/secondaryjoin`, иначе валится на старте.

**Деплой:** `../deploy_session96_multi_assignee.py`. Бэкапы `.bak_session96`,
снапшот прод-копий в `incident_547/server_backup_s96/`. Backfill через
`INSERT ... NOT EXISTS` идемпотентный — после деплоя 24 строки в
`incident_assignee`. Smoke 4/4 OK, лог чист.

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/models_legacy.py app/bootstrap.py app/children.py \
         app/templates/incident_edit.html app/templates/incidents_my.html \
         app/templates/incidents_registry.html; do
  cp "$f.bak_session96" "$f"
done
pkill -9 -f 'python3 run.py'
nohup setsid python3 run.py > /tmp/portal.log 2>&1 &
# Таблицу incident_assignee оставить — старый код её игнорирует.
```

См. `../memory/project_session96_multi_assignee.md`.

## Сессия 90a (28.04.2026) — MAX-бот: UX + security — ЗАДЕПЛОЕНО

Узкий sweep по MAX-боту перед большой сессией про вложения. 2 коммита:
- Бот (Amvera): `c9fee91` — `verify_signature` убирает проверку `X-Bot-Secret`
  (HMAC-подпись и так гарантирует знание секрета). Запушено в Amvera, контейнер
  пересобран.
- Портал: `9e404ca` (master) — 4 файла, бэкапы `.bak_session90a` на проде.

**Что вошло:**
- `/profile/max/status` (новый GET → JSON `{status:none|pending|done}`).
- `profile_max.html`: при `pending` — JS-poll этого endpoint каждые 3с,
  при смене статуса `location.reload()` (TTL polling 12 минут). Ручной F5
  больше не нужен.
- TTL pending bind на портале **1 час → 15 минут** (синхронно с
  `BIND_TTL_MIN=15` на боте). Текст «примерно 1 час» → «около 15 минут».
- `bot_client.py`: убран `X-Bot-Secret` из HMAC-заголовков. Остаётся
  `X-Bot-Timestamp` + `X-Bot-Signature`. Секрет в открытом виде по сети
  не передаётся.
- `scheduler.py`: brute-force защита MaxBinding code. In-memory счётчик
  неудач по `chat_id` (RLock как в `_LOGIN_ATTEMPTS`). Параметры:
  5 неудач за 5 минут → lockout 1ч. Перебор 6-значного кода с одного
  MAX-аккаунта замедляется с ~3 часов (1 попытка/сек) до ~5 лет.
  Сброс счётчика при успешной привязке.

**Порядок деплоя — критично:** бот первым. Старый бот требует
`X-Bot-Secret` → новый клиент без заголовка получит 401. Новый бот
лояльнее — старый клиент со «лишним» заголовком работает (бот его
игнорирует). `deploy_session90a.py` делает это в правильной
последовательности (push на Amvera → 90с ожидания пересборки →
paramiko на портал).

**Что НЕ сделано в этой сессии (отложено в s90b/s91):**
- (а) Скачивание вложений MAX → IncidentNote с файлами + libmagic/whitelist —
  большой кусок: бот endpoint `/api/attachment/<qid>/<idx>`, MAX API скачивание
  по token+url, портал-скачка через bot_client, валидация magic, рендер кнопок
  «скачать» в IncidentNote. Отдельная сессия минимум на 3-4 часа.
- P2 backlog аудита 280428: attendance.py:234,754 try/except, visit retention
  `synchronize_session='fetch'`, `/incidents/my` admin-table mobile card-mode,
  `/incidents/registry` карточный мобильный вид → s90b.

**Слабые места защиты MaxBinding (отложено):**
1. In-memory счётчик сбрасывается при рестарте портала. Для устойчивой
   защиты нужна таблица с retention. Пока — как `_LOGIN_ATTEMPTS`.
2. Атакующий меняет `chat_id` (новый MAX-аккаунт). MAX требует SMS-верификации,
   масштабирование атаки дорого, но идеального лимита нет.
3. На стороне бота нет своего троттлинга `/start <код>`. Вторая линия
   обороны — в s90b.

**Smoke на проде (admin):**
- /profile/max/status — `{status:none}` → после generate → `{status:pending}`
  → после revoke → `{status:none}`.
- /profile/max страница: setInterval только при pending, текст «около 15 минут».
- Все endpoint'ы 200/302, ошибок нет.

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/auth.py app/scheduler.py app/services/bot_client.py \
         app/templates/profile_max.html; do
  cp "$f.bak_session90a" "$f"
done
pkill -9 -f 'python3 run.py'; nohup setsid python3 run.py > /tmp/portal.log 2>&1 &
# Бот — git revert c9fee91 + git push amvera master
```

См. `../memory/project_session90a_done.md`.

## Сессия аудит-280428 (28.04.2026) — 4-агентский аудит + P0 — ЗАДЕПЛОЕНО

Read-only аудит 4 агентами в worktree-изоляции (backend / frontend+Playwright /
бот+security / инструкции БЗ). Внедрены P0 правки: 6 файлов кода + 4 файла
инструкций. Коммит `ec7f09f` на ветке `session/audit-280426` (master не трогали —
там uncommitted s90).

**P0 правки (10 файлов):**
- `app/tasks.py:1544` — open-redirect whitelist в `delete_task` (как в s80/s81 для incident_delete/edit).
- `app/templates/incidents_my.html:1573` — auto-list-view JS переписан под `data-view-tab`
  (старые `myBtnTable`/`myBtnList` ушли в s67-s72, мобильный авто-редирект на `?view=list` был мёртв).
- `app/templates/users_paths.html` — обе таблицы (топ-страниц, топ-переходов) обёрнуты в `.table-responsive`.
- `app/templates/layout.html` — cache-buster `?v=20260422m2/20260426` → `?v=20260428` для обоих CSS.
- `app/static/css/incidents-status.css` — `.filter-popup` mobile брейкпоинт `480px → 575.98px`
  + `!important` на position/left/right/width (перебивает inline JS-позиционирование) + z-index 1080.
- `app/static/css/app.css` — новое правило `@media (max-width: 419.98px)`:
  `.navbar-brand-wrap` ограничивает ширину `calc(100vw - 90px)`, `.brand-title .main`
  ellipsis, `.sub` скрыт. Решает горизонтальный скролл +14-29px, который шёл на каждой странице.
- 4 HTML инструкции в `app/static/guides/` (мастер-копия в `incident_547/инструкции/`):
  - `учитель/02_инцидент.html`, `классный_руководитель/02_инцидент.html` — 5 статусов в 3 этапах
    (Новый → Назначен → В работе → Отработан → Закрыт), 48ч окно вместо «пока статус Новый».
  - `классный_руководитель/03_класс.html` — добавлены пункты Кубок/ШСК/ДО в карточке ученика +
    FAQ переписан (класс.рук теперь ищет всех, может создавать инциденты по любому).
  - `психолог/02_инцидент.html` — психолог НЕ меняет статусы (право SP/DEPUTY/ADMIN), только
    «Я отработал» с обязательным комментом + опц. вложениями.

**Деплой:** `../deploy_audit_280428.py` (paramiko, бэкапы `.bak_session_audit_280428`).
Перед деплоем — dry-run `../preview_audit_280428.py` (диффы чистые, прод-версии = master HEAD).
После заливки `python3 run.py` упал (видимо OOM/SIGHUP при pkill), поднял заново
вручную (`nohup setsid`). Smoke 18/18 OK (7 HTTP + 11 file markers).

**Запускать с `PYTHONIOENCODING=utf-8`** — стрелка → ломает cp1251 на Windows.

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/tasks.py app/templates/incidents_my.html app/templates/users_paths.html \
         app/templates/layout.html app/static/css/incidents-status.css app/static/css/app.css \
         "app/static/guides/учитель/02_инцидент.html" \
         "app/static/guides/классный_руководитель/02_инцидент.html" \
         "app/static/guides/классный_руководитель/03_класс.html" \
         "app/static/guides/психолог/02_инцидент.html"; do
  cp "$f.bak_session_audit_280428" "$f"
done
pkill -9 -f 'python3 run.py'; nohup setsid python3 run.py > /tmp/portal.log 2>&1 &
```

**False positives агентов** (что НЕ правил):
- A: CSRF в 166 шаблонах — layout.html инжектит токен через JS глобально (s25).
- A: incidents_registry без .table-responsive — false, обёртка уже есть на 317.
- B: эмодзи 👤🔑🔔💬 в profile_settings и в extracurricular_hub — в исходниках UTF-8 эмодзи нет (видимо bi-icons в рендере).
- D: «прерогатива классного руководителя» в психолог/03_класс — в файле такой формулировки нет.

**P1/P2 в backlog (не в этой сессии):**
- bot.py: SHARED_SECRET передаётся в каждом HTTP-заголовке вместе с подписью — лишнее.
- auth.py (s90 файл): brute-force MaxBinding code (нет счётчика на портале).
- scheduler.py (s90 файл): race в `_poll_bot_queue` (UPDATE без commit между ними).
- attendance.py:234, 754: try/except на delete/commit.
- Inline-рендер .pdf/.txt/.gif без libmagic в children.py:3262.
- SESSION_COOKIE_SECURE=False — ждёт HTTPS на проде.
- Инструкции: 17+ хвостов P1 (admin под s58/s60/s68/s72/s78/s86, разделы Кубок/ШСК/ДО,
  гайд /profile/notifications, гайд «Привязка MAX-бота» — ПОСЛЕ фикса вложений в s90).
- Инструкций нет вовсе для SOCIAL_PEDAGOG, METHODIST, DEPUTY_DIRECTOR.

См. `../memory/project_session_audit_280428.md`.

## Сессия 89 (27.04.2026) — единый /extracurricular + фильтр программ — ЗАДЕПЛОЕНО

Раздел «Доп. образование» как единый хаб ШСК+ДО+Кубок. 4 NEW + 5 EDIT файлов,
без миграций БД. Деплой `../deploy_session89.py` + 3 hotfix-итерации поверх.

- **`/extracurricular/`** — общий свод (3 счётчика, по параллелям/зданиям, по
  классам). Доступ: ADMIN/SOCIAL_PEDAGOG/METHODIST = вся школа,
  CLASS_TEACHER = только свой класс через `teacher_user_id`+is_active+current
  year. TEACHER/PSYCHOLOGIST → 403.
- **`/extracurricular/do`** — фильтр по программе. 350 сырых → 242
  канонизованных (объединены по «название + параллель»).
  `_canonicalize_program(raw)` срезает `25/26`/`группа NN`/литеры класса
  (`7ФГ`/`8 АН`/`9-БШ`)/параллель, возвращает `(base, parallel)`. UI:
  `<select>` (col-md-5) + `<input list>` со свободным вводом + datalist +
  кнопка «Найти» (col-md-7 col-auto). Свободный ввод сравнивается по
  каноническому ключу. При выбранной программе таблица «По классам»
  скрывает классы с 0 записанных. Процент `'%.1f'` (раньше `// 100` давало
  0% при малых значениях).
- **`/extracurricular/sport-club`** — ШСК.
- **`/extracurricular/export.xlsx?section=summary|do|sport-club&program=...`** —
  Excel. Колонка «Кубок» только ADMIN.
- **Плитка «Доп. образование»** в `secondary_sections` для тех же 4 ролей.
- **`/contingent` + `/classes`**: убраны 3 колонки (ШСК/ДО/Кубок). В шапке
  /contingent — кнопка «Доп. образование». Backend `contingent()` не
  трогал (sc_by_class/do_by_class всё ещё считаются — почистить в s90+).
- Из свода удалена странная карточка «Кубок школы → Открыть рейтинг»
  (вела на /classes, не на рейтинг). Кубок остался колонкой в таблице
  «По классам» под admin.

**Файлы (4 NEW + 5 EDIT):**
```
NEW  app/extracurricular_hub.py
NEW  app/templates/extracurricular_hub.html
NEW  app/templates/extracurricular_do.html
NEW  app/templates/extracurricular_sport_club.html
EDIT app/extracurricular.py                       (canonicalize, list_programs, count_in_program)
EDIT app/modules/__init__.py                      (+blueprint)
EDIT app/modules/hub/routes.py                    (плитка + ICON_MAP + zone)
EDIT app/templates/contingent.html                (-3 колонки + ссылка на хаб)
EDIT app/templates/classes_list.html              (-3 колонки)
```

Источники переиспользованы: `sport_club.count_in_club_for_children`,
`extracurricular.count_in_do_for_children`, `kubok.get_rating`.

**Smoke (admin на проде):**
- `/extracurricular/` 200, 116 классов, 179kb
- `/extracurricular/do` 200, 242 опции в datalist+select
- `/extracurricular/export.xlsx?section=summary` 200, ~10kb
- `/contingent` 200 без 3 колонок
- `/classes` 200 без 3 колонок

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/modules/__init__.py app/modules/hub/routes.py \
         app/templates/contingent.html app/templates/classes_list.html; do
  cp "$f.bak_session89" "$f"
done
cp app/extracurricular.py.bak_session89b app/extracurricular.py
rm app/extracurricular_hub.py app/templates/extracurricular_hub.html \
   app/templates/extracurricular_do.html app/templates/extracurricular_sport_club.html
pkill -9 -f 'python3 run.py'; nohup setsid python3 run.py > /tmp/portal.log 2>&1 &
```

См. `../memory/project_session89_done.md` (детальный лог 4 итераций).

## Следующая сессия (s90, 28.04.2026)

См. `../memory/project_session90_plan.md`. Две темы:
1. MAX-бот: скачивание вложений, авто-апдейт `/profile/max` без F5,
   согласование TTL pending binds.
2. Докрутка ДО: список программ как отдельный экран, students по программе,
   «кого дотянуть» для класс.рука, чистка backend `/contingent`.

## Сессия 87 (27.04.2026) — соц.паспорт класса/сводный + SP-права + Я отработал — ЗАДЕПЛОЕНО

8 файлов, коммит `7977fa2`, бэкапы `.bak_session87`, deploy `deploy_session87.py`,
smoke OK, лог чист. ALTER TABLE child_social прошёл (4 новых колонки на проде).

**Три задачи директора:**
1. **Кнопка «Я отработал» в карточке инцидента** не сохраняла. Root cause:
   JS-инициализатор `markResolved` стоял в `<script>` ВЫШЕ модалки в DOM —
   `getElementById('markResolvedSubmit')` возвращал null на parse-time,
   listener не вешался. Фикс: завернул в `DOMContentLoaded` (incident_edit.html).
2. **SOCIAL_PEDAGOG права как у ADMIN** на статусы/assignee.
   `_can_change_status()` в `children.py` теперь
   ADMIN | DEPUTY_DIRECTOR | SOCIAL_PEDAGOG. Каскадно отключает старый
   `is_social_view` (4-я вкладка «Назначенные мне» уходит, появляется picker
   и status-pill во всех видах).
3. **Соц.паспорт класса + сводная по школе** для соц.педагога/классрука:
   - **+4 поля в `ChildSocial`** (миграция через `bootstrap.py` ALTER ...
     DEFAULT FALSE): `is_single_mother`, `is_single_father`, `is_repeat_year`,
     `is_svo_family`. Дети-инвалиды и ОВЗ берутся с Child (`is_disabled`,
     `is_ovz`) — не дублируем.
   - **13 категорий** по docx-шаблону директора (`SOCIAL_PASSPORT_CATEGORIES`):
     многодетная, неполная (по подстроке `family_status`), мать-одиночка,
     отец-одиночка, родители-инвалиды, дети-инвалиды, опека, повторный курс,
     ОВЗ, малообеспеченные, ВШУ/КДН/ПДН, сирота, СВО.
   - **`/social-passport/class/<class_id>`** — таблица 1-в-1 как docx:
     ФИО+тел., дата рождения, адрес рег./факт., родители (ФИО+тел.),
     13 столбцов с галочками + строка итогов + ФИО и тел. кл.рук в подвале.
     Кнопка «Печать». ADMIN/METHODIST/SP — любой класс, CLASS_TEACHER —
     только свой.
   - **`/social-passport/summary`** — 4 вкладки: classes/parallels/buildings/school.
     ADMIN/METHODIST/SP.
   - В существующий `/social-passport` (per-child) добавлены кнопки
     «Паспорт класса» (когда выбран class_id) и «Сводная».
   - Class teacher уже мог заполнять per-child паспорт — соц.паспорт класса
     автоматически собирается из суммы детских.

**Файлы (8):**
```
app/bootstrap.py                              (+4 ALTER child_social)
app/models_legacy.py                          (+4 поля ChildSocial)
app/children.py                               (SP в _can_change_status, 2 новых
                                              route + helpers, +4 чекбокса в POST)
app/templates/incident_edit.html              (markResolved → DOMContentLoaded)
app/templates/child_card.html                 (+4 чекбокса)
app/templates/social_passport_registry.html   (кнопки навигации)
app/templates/social_passport_class.html      (NEW)
app/templates/social_passport_summary.html    (NEW)
```

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/bootstrap.py app/models_legacy.py app/children.py \
         app/templates/incident_edit.html app/templates/child_card.html \
         app/templates/social_passport_registry.html; do
  cp "$f.bak_session87" "$f"
done
rm app/templates/social_passport_class.html app/templates/social_passport_summary.html
pkill -9 -f 'python3 run.py'; nohup setsid python3 run.py > /tmp/portal.log 2>&1 &
# Колонки можно оставить (DEFAULT FALSE, старый код их не трогает).
```

См. `../memory/project_session87_social_passport.md`.

## Сессия 86 (27.04.2026) — MAX-бот, ЗАДЕПЛОЕНО (бот + портал)

MVP бота для подачи инцидентов через мессенджер MAX. Polling-архитектура:
портал каждые 15с тянет очередь у бота на Amvera, школьный сервер не публикуется.

- **Бот** на Amvera: `bot-incident-ivanbiletskiy.amvera.io`, `@reguestsbot`,
  репо `c:/Users/bilec/Desktop/Claude code проекты/bot-incident-547/`.
- **Портал**, 7 файлов (бэкапы `.bak_session86`):
  - `app/models/max_binding.py` (NEW), `app/models/__init__.py` (импорт)
  - `app/services/bot_client.py` (NEW, HMAC)
  - `app/auth.py` (3 endpoint: `/profile/max`, `/profile/max/generate`, `/profile/max/revoke`)
  - `app/scheduler.py` (job `poll_bot_queue` 15s + helper `_bind_payload_for_user`)
  - `app/templates/profile_max.html` (NEW), `app/templates/profile_settings.html` (вкладка)
- **ENV** в `/home/user/portal/.env` (бэкап `.env.bak_session86`):
  `BOT_API_URL`, `BOT_SHARED_SECRET`, `PORTAL_BASE_URL`.
- **Без миграций БД**: `max_binding` через `db.create_all()`.

**Что работает:** привязка кодом (TTL 1 час, МСК), мастер инцидента (класс →
ученик → категория → описание + вложения → дата + 48ч окно → подтверждение),
создание Incident через job (МСК-время, поиск ученика по `student_query`
для admin/SP/deputy через подстроку last_name/first_name), ack пользователю
в MAX.

**Что отложено:** скачивание вложений (пока IncidentNote с количеством),
автообновление страницы `/profile/max` без F5, согласование TTL pending
binds бот↔портал (бот 15м, портал 60м).

См. `../memory/project_session86_max_bot.md` (детальный лог + 5 hotfix-итераций
в той же сессии: pip-зеркало Amvera, домен на Amvera, `archived`→`is_archived`,
`kb.as_markup()`, `astimezone(Europe/Moscow)`, TTL+МСК).

Deploy: `../deploy_session86.py`.

## Сессия 85 (27.04.2026) — ЗАДЕПЛОЕНО

Perf-фиксы по аудиту s84 (3 агента). 6 файлов, коммит `bd27712` + hotfix `00956cd`
(вернул ветвление крошек /incidents/my admin↔user). Бэкапы `.bak_session85` +
`.bak_s85_breadcrumb`. Smoke 9/9 OK.

- **+11 индексов** в `bootstrap.py` через `CREATE INDEX IF NOT EXISTS`:
  incident_notification user-unread, task user-unread, task responsible/status,
  task status/deadline, user employment_status, school_class year/archived,
  child_enrollment status + class/status, child status, child_events from_class
  + event_type/from_class.
- **`registry_expelled` + export** (`children.py`): N+1 убран — `Child.query.filter(id.in_([...]))`
  вместо `.query.get()` в цикле.
- **`/management/dashboard`** (`management.py`): `Counter(e.school_class_id)` вместо
  O(116×3400) Python-цикла в `summary['free_places']`.
- **`/orders/`** (`orders.py`): `selectinload(responsible_links).joinedload(user)`
  убирает N+1.
- **`/diagnostics/`** (index + analytics): фильтр→batch вместо N+1. `index()` теперь
  сначала фильтрует сессии, потом одним SELECT visible_results на отфильтрованный
  набор, GROUP BY на imports count, DISTINCT на наличие results — было 4×N запросов,
  стало ~3 всего. `analytics()` фильтрует session_id в SQL до `.all()`.
- **`/control-works/registry`** (`control_works.py`): `_build_work_registry_row`
  теперь принимает `precomputed_results` и `precomputed_total_students` (None →
  fallback). `_build_registry_dataset` делает один SELECT на все ControlWorkResult,
  один GROUP BY на enrollment counts по парам (year_id, class_id), eager-load
  assignments + school_class/teacher/creator/updater/subject_ref. Было 5×N запросов
  на ~300 работ (~1500), стало 3 всего.

**Прогретый кеш на проде (admin):** /control-works/registry 104 ms, /diagnostics/analytics
68 ms, /registry/expelled 79 ms, /orders/ 91 ms, /diagnostics/ 111 ms.

**Hotfix крошек /incidents/my:** в s83 убрал ветвление в пользу единого «Мои заявки»,
но для admin/SP заголовок страницы — «Инциденты», и крошка должна совпадать.
Возвращён `is_admin_view`-условие.

**P0 #5 page_visit batch-flush** и **P0 #6 extract incidents_my.html inline CSS/JS**
(1500+ строк) — отложены отдельной сессией (риск регрессии).

См. `../memory/project_session85_perf.md`.

## Следующая сессия (s86) — MAX-бот подачи инцидентов

См. `../memory/project_session86_max_bot_plan.md`,
`../memory/project_max_bot_plan.md`, `../memory/reference_amvera_bots.md`.

## Сессия 84 (27.04.2026) — ЗАДЕПЛОЕНО

48-часовое окно подачи инцидента задним числом. 2 файла, коммит `dbfcbb7`,
бэкапы `.bak_session84`.

- `incident_new` POST — для всех ролей: `now-48h ≤ occurred_at ≤ now+5min`,
  иначе flash + редирект.
- `incident_edit` POST — то же окно с исключением для `is_admin` и
  `DEPUTY_DIRECTOR` (могут править дату вне окна для исправления).
- UI: alert-warning сверху формы + form-text под датой + JS `min`/`max` на
  `input[type=date]`.

См. `../memory/project_session84_48h_window.md`.

## Сессия 83 (27.04.2026) — ЗАДЕПЛОЕНО

Правка хлебных крошек (9 пунктов одним пакетом). 6 файлов, коммит `9967177`,
бэкапы `.bak_session83`. См. `../memory/project_session83_done.md`.

## Сессия 82 (27.04.2026) — ЗАДЕПЛОЕНО

7 файлов, коммит `7659bbe` на master. `../deploy_session82.py`,
бэкапы `.bak_session82`, smoke 5/5 OK на проде.

**Этапы статусов (запрос директора):** 5 сырых статусов сгруппированы в 3 этапа.
- Открытые: `new`
- В работе: `assigned`, `in_progress`
- Закрытые: `resolved`, `closed`

Поправлено везде: status-picker меню в `/incidents/my` и `/incidents/registry`
(новые `<div class="sp-group">Открытые/В работе/Закрытые</div>` с правильным
распределением `sp-opt`); чарт «По статусу» на дашборде через
`data-sb-bucket="open|in_work|closed_total"` + Jinja-агрегация
`sb_open=new`, `sb_in_work=assigned+in_progress`,
`sb_closed_total=resolved+closed`; `renderStatusStats()` пересчитывает
`window.__statusCounts` по бакетам.

`STATUS_BUCKETS` в `children.py:4480` уже совпадал с этапами директора
(incoming=[new], in_work=[assigned,in_progress], completed=[resolved,closed]) —
kanban-колонки и счётчики не трогали.

**Kanban: ручная смена статуса переносит карточку в колонку этапа.**
В обработчике клика по `.sp-opt` в `incidents_my.html` после успешного
`set-status` определяем целевой бакет через `STATUS_TO_BUCKET` и переносим
карточку в `kb-col-body[data-bucket=...]`, обновляя счётчики обеих колонок.
Раньше менялся только pill — UX-баг.

**P1.8 bootstrap.js defer:** 3 inline-IIFE с `new bootstrap.Modal()` обёрнуты
в `DOMContentLoaded` (incidents_dashboard.html:942, incidents_my.html:1828,
incidents_registry.html:1042). 4-й (role_access_settings.html:286) уже был
обёрнут. На `bootstrap.bundle.min.js` в `layout.html:13` добавлен `defer`.

**P2 backlog:**
- #3 sp-group английские лейблы (To-do/In progress/Complete) → русские
  и переставлены под этапы.
- #5 METHODIST mobile в `/registry`: per-row `_row_editable`,
  карандаш↔глаз, корзина прячется на чужих. `children.py:4280` +
  `is_methodist=has_role("METHODIST")`.
- #7 «— выбрать —» в `child_card.html:1153/1449/1504` →
  «Выберите предмет/раздел/класс».
- #1 `control_works.py:1762` `work_query.distinct().count()` →
  `.order_by(None).distinct().count()` (защита от GroupingError на PG).
- #2 `tasks.py:815` — план соврал, там уже SQL GROUP BY. Не правил.

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/children.py app/control_works.py \
         app/templates/layout.html app/templates/incidents_dashboard.html \
         app/templates/incidents_my.html app/templates/incidents_registry.html \
         app/templates/child_card.html; do
  cp "$f.bak_session82" "$f"
done
pkill -9 -f 'python3 run.py'; nohup setsid python3 run.py > /tmp/portal.log 2>&1 &
```

См. `../memory/project_session82_done.md`.

## Сессия 81 (27.04.2026) — ЗАДЕПЛОЕНО

P1-фиксы поверх s67-s80+s66. 6 файлов, без миграций (UNIQUE через
`CREATE UNIQUE INDEX IF NOT EXISTS` в bootstrap.py). Бэкапы `.bak_session81`.
Скрипт: `../deploy_session81.py`. Smoke 6/6 OK, лог чист, маркеры в шаблоне
на месте.

- **P1.2 N+1 на kanban** — `_build_incident_rows` (children.py:3464) делает
  батч `joinedload(Incident.assignee, Incident.author)` в session cache до
  основной обработки. На 600 карточках экономия до 1200 запросов.
- **P1.3 SavedView race + UNIQUE** — `models/saved_view.py:27` получил
  `UniqueConstraint(user_id, scope, name)`, `saved_views.py:75` ловит
  `IntegrityError` на двойном клике (возвращает существующий вид как `ok`),
  `bootstrap.py:208` создаёт `uq_saved_view_user_scope_name` через
  `CREATE UNIQUE INDEX IF NOT EXISTS`. На проде индекс встал.
- **P1.4 race в tasks.py change_status** — `Task.query.filter_by(id=task_id).with_for_update().first()`
  + `abort(404)` вместо `get_or_404`. Row-lock на PG, no-op на SQLite.
- **P1.5 open-redirect в incident_edit POST** (children.py:3691) —
  `not next_url.startswith("//")` блокирует schema-relative `//evil.com`.
  В `incident_delete` фикс уже стоял с s80.
- **P1.6 эмодзи 📅/👤 в kanban kp-prop** (incidents_my.html:989-993) —
  заменены на `<i class="bi bi-calendar-event">` и `<i class="bi bi-person">`.
  Правило `feedback_no_visual_overload`.
- **P1.7 myMarkResolvedModal** (incidents_my.html:1746) получил
  `modal-fullscreen-sm-down` (как у setAssigneeModal/incidentDeleteModal) —
  на <576px ввод comment+файлов теперь в полноэкранном режиме.

**P1.1 (page_visit retention) — план был неверным.** На проде колонка
`ts` (как в модели), retention в `scheduler.py:47` через
`PageVisit.ts < cutoff` корректен. На проде 2133 записи за 5 дней
(~13к/мес — норма). `visited_at` нигде не существует — фикс не нужен.

**P1.8 (bootstrap.js defer) — отложен на s82.** План соврал «все IIFE
завёрнуты»: 4 inline-IIFE используют `new bootstrap.Modal()` на parse-time
(incidents_dashboard:945, incidents_registry:1046, incidents_my:1832,
role_access_settings:289). С `defer` упадут с `bootstrap is not defined`.
Сначала надо обернуть в `DOMContentLoaded`.

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/children.py app/saved_views.py app/models/saved_view.py \
         app/bootstrap.py app/tasks.py app/templates/incidents_my.html; do
  cp "$f.bak_session81" "$f"
done
pkill -9 -f 'python3 run.py'; nohup setsid python3 run.py > /tmp/portal.log 2>&1 &
# UNIQUE INDEX оставить — безопасен.
```

См. `../memory/project_session81_done.md`.

## Деплой 27.04.2026 — s67-s80 + s66 — ЗАДЕПЛОЕНО

Большой накопленный деплой (16 файлов, 14 из `deploy_session67_79.py` + 3 для s66).
В процессе — 2 регрессии на проде PG, обе пофикшены на лету:

1. **`BuildError: auth.profile_settings`** — `layout.html` (s80) ссылался на
   эндпоинт из s66, которого не было в `deploy_session67_79.py`. Откатил
   `layout.html` на бэкап, потом дозалил s66 целиком (`auth.py` +
   `profile_settings.html` + s80-`layout.html`), бэкапы `.bak_session66`.
2. **`psycopg2 GroupingError: column "incident.occurred_at" must appear in
   GROUP BY clause`** в `children.py:4214,4659` — пагинация COUNT с висячим
   `order_by` от родительского query. Фикс:
   `.order_by(None).with_entities(func.count(...))`.

Аудит после фиксов (3 агента, см. `../memory/project_session_deploy_27apr.md`
и `project_session81_plan.md`): **P0 нет**, 8 P1 → s81, P2 backlog 7 пунктов.

**P1 на s81:**
1. `page_visit` retention 30d сломан (s49) — колонка `visited_at` не
   существует в схеме. Таблица растёт.
2. N+1 на `/incidents/my?view=kanban` — `_build_incident_rows`
   (`children.py:3459`) не eager-loadит `Incident.assignee/author`.
3. SavedView нет UNIQUE(user_id, scope, name) + race в saved_views.
4. Race в `tasks.py` (нет `with_for_update()`).
5. Open-redirect в `incident_edit` POST (`children.py:3683`) — пускает
   `//evil.com`. В `incident_delete` уже починили.
6. Эмодзи 📅/👤 в kanban kb-prop (`incidents_my.html:989-993`) — нарушение
   `feedback_no_visual_overload.md`.
7. `myMarkResolvedModal` без `modal-fullscreen-sm-down` (`incidents_my.html:1745`).
8. `bootstrap.bundle.min.js` в `<head>` без `defer` (`layout.html:13`).

**P2 backlog (s82+):** `control_works.py:1762` count без order_by(None);
`tasks.py:815` агрегация в Python вместо GROUP BY; SP-группы picker'а на
англ (incidents_my:1006/1010/1014); group/sort на дашборде; METHODIST
mobile в /registry; роль в шапке через одиночное поле; «— выбрать —» в
child_card; нет тест-юзеров на проде.

**Бэкапы на проде:** `.bak_session67_79` (12) + `.bak_session66` (2) +
hotfix через те же файлы (children.py перезалит поверх).

См. `../memory/project_session_deploy_27apr.md` — детали хронологии.

## Сессия 80 (26.04.2026) — Аудит s67-s79 + P0/P1 фиксы перед деплоем — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

Перед общим деплоем накопленных s67-s79 — параллельный аудит тремя агентами
(backend / frontend / regression-QA) в worktree `.claude/worktrees/audit-{backend,frontend,regression}`
от master `a16a0c5`. Артефакты — `audit_report.md` в каждом worktree.

**Главный баг (директор сообщил):** при попытке сменить статус инцидента
через пилюлю в kanban — статус «прыгает» между соседними карточками. На скрине
(после первого фикса) — открытое меню перекрывалось зелёной плашкой «Закрыт»
соседней карточки, опции `Закрыт` появлялись в чужих секциях `In progress`.

**Root cause** — двойной:
1. `.kb-card:hover { transform: translateY(-1px) }` срабатывает на соседях во
   время drag → подъём/опускание соседей вызывает «дрожь» status-pill.
2. На hover карточка получает `transform`, что создаёт у неё новый
   stacking context. Меню `.status-picker-menu` (z-index:1050) клипается
   контекстом своей kb-card, а соседние kb-card на :hover тоже создают
   стек-контекст — их `.status-pill` (DOM-позже) рисуются ПОВЕРХ нашего меню.

**Фикс (3 слоя в `incidents_my.html`):**
- CSS-overrides `.inc-kanban.kb-dragging-active .kb-card:hover { transform:none }`
  — глушат hover-jitter на время D&D.
- CSS `.kb-card.kb-menu-open { position:relative; z-index:1200 }` +
  `.kb-card.kb-menu-open:hover { transform:none }` +
  `.inc-kanban:has(.status-picker-menu.open) .kb-card:hover { transform:none }`
  — поднимают карточку с открытым меню над соседями, гасят transform у всех.
- JS toggle класса `.kb-menu-open` на kb-card на open/close меню (клик по
  пилюле, выбор опции, клик-вне, dragstart).
- В `dragstart` дополнительно: `kbBoard.classList.add('kb-dragging-active')`
  + сброс открытых status-меню (иначе зависают на старой позиции карты).

**P0 #2: kanban status-picker сломан.** Старая разметка kanban — `data-incident-id`
на корне `.status-picker`, `data-value` на `.sp-opt`. Старый JS читал
`opt.dataset.incidentId/status` → `POST /incidents/undefined/set-status`.
Фикс с обратной совместимостью для table/list (где те же атрибуты были на opt):
`var id = pk.dataset.incidentId || opt.dataset.incidentId || btn.dataset.incidentId`,
`var status = opt.dataset.value || opt.dataset.status`. Также добавлен
CSRF-заголовок (раньше его не было в picker'е, был только в D&D).
Подтверждено локально: `POST /incidents/21/set-status` → `{ok:true,status:in_progress}`.

**P1 #1: Open redirect в `incident_delete`.** `next` принимал любой
`http(s)://...`. Усугублялось s76 (METHODIST дотягивался до пути).
Фикс: только `next_url.startswith("/") and not next_url.startswith("//")`.

**P1 #2: METHODIST мог удалять свои инциденты.** После s76 `incident_add`
для METHODIST `_can_edit_incident` возвращал True для author/assignee, и
`incident_delete` пускал. Фикс: явный gate
`if has_role("METHODIST") and not _can_change_status() and not has_role("SOCIAL_PEDAGOG"): abort(403)`
после `_can_edit_incident` в `incident_delete`. METHODIST по-прежнему может
edit-свои (по решению директора в s76), но не delete.

**P1 #3: `.status-pill / .status-picker-menu / .sp-opt` без `draggable=false`.**
В kanban находятся внутри `.kb-card[draggable="true"]` — на неточном клике
ловили dragstart. Добавлено в kanban-разметке.

**P1 #4: Мёртвый код после `return`** — IIFE с legacy collapse-логикой
~58 строк после `endblock` (s71 наследие, s72 переписал на seamless).
Удалён целиком.

**P1 #5: `view=list` в попапе создаёт пустую страницу** — false positive
у regression-агента: ветка `else` на строке 1212 рендерит list корректно
(`elif view_mode != 'list'` — табл; `else` — лист). Бага нет.

**Аудит выявил для следующих сессий (P1 backend, отложены):**
- N+1 на /incidents/my kanban (600 карточек × author/assignee = до 1200 запросов)
- Counters /my всегда школьно-широкие (для SP с tab=mine не совпадают с доской)
- SavedView race + нет UNIQUE на (user, scope, name)
- bootstrap.js в `<head>` без `defer` (из s70)

**Файлы для деплоя s67-s79 (14 = 12 изменённых + 2 новых):**
```
app/permissions.py
app/children.py
app/core/context_processors.py
app/saved_views.py                        (NEW)
app/models/__init__.py
app/models/saved_view.py                  (NEW)
app/modules/__init__.py
app/static/css/incidents-status.css
app/templates/layout.html
app/templates/incident_edit.html
app/templates/incident_new.html
app/templates/incidents_dashboard.html
app/templates/incidents_my.html
app/templates/incidents_registry.html
```

Без миграций (SavedView через `db.create_all()`, индексы s63b через
`CREATE INDEX IF NOT EXISTS` в bootstrap.py). Деплой-скрипт:
`../deploy_session67_79.py` (paramiko, бэкапы `.bak_session67_79`,
рестарт + smoke admin/methodist).

**Smoke локально (admin, :5001) — OK:** все 7 страниц 200, маркеры фиксов
в HTML (`kb-dragging-active` 4×, `kb-menu-open` 7×, `z-index:1200` 1×,
`has(.status-picker-menu.open)` 1×, `draggable="false"` на status-pill 31×,
старого dead IIFE 0×), `POST /incidents/<id>/set-status` 200 + JSON.

**Деплой — 27.04.2026** (школьный WiFi). Перед заливкой шаблонов сверять
с продом (правило `feedback_deploy_over_prod.md`).

См. `../memory/project_session80_audit_fixes.md`.

## Сессия 78 (26.04.2026) — Calendar view + фикс «4-я вкладка не появляется» — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

Поверх s77. Только `/incidents/my`. 2 файла, без миграции БД. Коммит `fa7f85a`.

**Главный баг (s77 регрессия).** В s77 кнопку `+ Создать вид` обернули в
`<span>` для popup-позиционирования. JS делал
`nvBar.insertBefore(chip, nvCreateBtn)` — `nvCreateBtn` стал внуком `nvBar`,
не прямым потомком, `insertBefore` падал с `NotFoundError`, сохранённый чип
молча не появлялся. Фикс: вставлять перед wrapper-ом.

**4-я постоянная вкладка «Календарь»** в `view-tabs-bar` рядом с
Таблица/Доска/Список (`bi-calendar3`). Видна сразу, не требует создания
именного вида.

**Реальный календарный рендер (вместо плейсхолдер-баннера s77).**
- Backend: `?month=YYYY-MM` парсится по **Europe/Moscow** (zoneinfo
  с fallback UTC+3), default — текущий месяц МСК. `iq.filter(occurred_at
  >= first_day, < next_first)`. Отдельная ветка пагинации:
  `iq.order_by(occurred_at.asc()).limit(2000)` без offset. `cal_ctx.weeks`
  через `calendar.Calendar(firstweekday=0).monthdatescalendar` — 7 дней Пн-Вс.
- Template: CSS `.cal-grid` 7×N, цветные плашки `.cal-evt.s-{status}`
  (синий new / амбер assigned / фиолет in_progress|resolved / зелёный closed),
  `cal-today` — оранжевый круг по МСК. Toolbar: ← Месяц | название |
  Месяц → + «Сегодня» + счётчик. До 5 событий в ячейке + «+ ещё N».
  Tooltip — статус + 120 симв описания. Клик → `incident_edit`.
- Табличная панель (table/list/kanban) обёрнута в
  `{% if view_mode != 'calendar' %}` — не рендерится в календаре.

**Сохранение календарного вида.** `view=calendar` сохраняется в `qs`,
но `month` НЕ в whitelist `_normalize_qs` — saved view всегда открывает
текущий месяц МСК (осознанно: «календарь сейчас», а не «календарь апреля»).

**Файлы (2):**
```
app/children.py                       (is_calendar, MSK-парс ?month=,
                                       фильтр по месяцу, cal_ctx с weeks)
app/templates/incidents_my.html       (4-я вкладка, CSS .cal-*, рендер сетки,
                                       insertBefore-фикс, обёртка панели)
```

py_compile + jinja-parse — OK. Локальный smoke (admin/admin123, :5001):
`/incidents/my?view=calendar` 200 (40 cal-cell, 15 cal-evt, cal-today,
активная 4-я вкладка), `?view=table` 200 (`<table>` есть; в calendar — нет),
POST `/api/saved-views` `qs=view=calendar` 200.

В следующей сессии — финальные правки + общий деплой s67-s79.

См. `../memory/project_session78_calendar_view.md`.

## Сессия 77 (26.04.2026) — Notion-pill Sort + 2-step View Creator — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

Поверх s76. Только `/incidents/my`. 2 файла, без миграции БД.

**Sort-dropdown переделан в pill+picker (вместо стопки ↑/↓ в одной колонке).**
- Активная сортировка: pill `[Свойство][↑/↓ Возр./Убыв.][×]` + ссылка
  «+ Сменить свойство» (раскрывает picker свойств).
- Без сортировки: сразу picker (клик → asc по умолчанию).
- В v2-дропдауне (`.sort-dropdown-v2`) клик делает `location.href = ...`
  вместо `history.replaceState` — чтобы шаблон пересобрал pill.
- Все элементы остались `js-sort-opt` + `data-sort` — JS-логика
  (compareBy/applySort) не тронута.

**View Creator: 2-шаговый popup (вместо inline-input).**
- Шаг 1: сетка 2×2 — Таблица / Доска / Список / Календарь.
- Шаг 2: input «Название · {тип}» + «Назад» / «Готово». Пустое имя →
  «Новый вид». POST `/api/saved-views?qs=...&view=<тип>`. Esc/клик-вне закрывают.

**Calendar — placeholder.**
- `app/children.py:4493` — `view_mode_raw in ("table","list","calendar")`
  (added 'calendar'). Запрос идёт по той же ветке что table.
- В шаблоне над контентом `view_mode == 'calendar'` — синий info-баннер
  «в разработке, пока показывается таблица». Полноценный календарь —
  отдельной сессией.

**Файлы (2):**
```
app/children.py                       (+'calendar' в кортеж, 1 строка)
app/templates/incidents_my.html       (CSS sort-v2 + nv-popup +
                                       calendar-pending-banner; HTML
                                       двух sort-меню; HTML nv-popup;
                                       JS переписан под 2-step + dir
                                       reload + change-prop)
```

py_compile + jinja-parse — OK. Пользователь визуально проверял на :5001.

См. `../memory/project_session77_notion_sort_view.md`.

## Сессия 76 (26.04.2026) — METHODIST + P2 + Notion Sort — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

Поверх s74 (`f5c8912`). s75 **откачен** (директор: «хрень какая-то, плашку SP не надо»).

**Что сделано:**

### Откат s75
- `git checkout` 3 файла. SP-плашка «Назначено на меня», kanban-сортировка «мои сверху», disabled-tooltip в /registry — убраны.

### METHODIST: создание + редактирование своих
- `app/permissions.py` — METHODIST в `incident_add`.
- `app/children.py` `_can_edit_incident` — теперь `incident_add` + (author OR assignee). Раньше только author.
- `incidents_my()` — `can_edit_rows = True` для METHODIST (было False).
- Шаблон: «+ Новый инцидент» возвращён, per-row gate `_row_editable` в table+list — карандаш↔глаз, корзина прячется на чужих.

### P2 (закрыты все хвосты аудита s73)
- **P2-1 пагинация** `/incidents/registry` — 100/стр, distinct count + подзапрос id+occurred_at, joinedload по итоговым ID. UI: nav внизу + счётчик «N из M · стр. K/L» вверху (с `text-truncate min-width:0` — фикс мобильного P2-3).
- **P2-2 русские категории** — DB содержит легаси-коды (`conflict`, `absence`, `other`, `property_damage`). `INCIDENT_CATEGORY_LEGACY` map + `_category_label()` в children.py + Jinja-глобал `incident_category_label` в `core/context_processors.py`. Применён в 5 видимых местах + в `_group_incident_rows(group_by='category')`.
- **P2-3** мобильный счётчик — закрыт вместе с P2-1 (новый формат).
- **P2-4** dashboard popup-фильтры — уже сделан в s74.

### Notion-style Sort dropdown (во все 3 вида + registry)
- Кнопка «Сортировка» с `bi-arrow-down-up` между Group и Filter — в `/incidents/my` (table/kanban/list) и `/incidents/registry`.
- Меню: «Без сортировки» + 6 свойств (Дата / Категория / Класс / Здание / Исполнитель / Статус), для каждого две стрелки `↑` (asc) `↓` (desc). В Доске «Статус» скрыт (статус = колонки).
- Sort key `<prop>_<asc|desc>`. JS `compareBy()` парсит → `{prop, dir±1}`, сравнивает по data-attrs (`data-occurred`, `data-category`, `data-class`, `data-building`, `data-assignee-label`, `data-status` со STATUS_RANK), `localeCompare('ru')` для текста.
- Бесшовно: DOM-перестановка внутри `tbody` / `.inc-list-group-body` / `.kb-col-body`. Если активна группировка — сортировка внутри подгрупп.
- Persistence: localStorage (`incidents_my_sort_v1` / `incidents_registry_sort_v1`) + URL `?sort=` через `history.replaceState`. Старое поле «Сортировка» из filter-popup убрано.
- Активная стрелка `#fff1e6 / #c25b00 / #fed7aa`. На кнопке — точка-индикатор + метка «Сорт.: Дата ↓».

**Файлы (6):**
```
app/permissions.py                       (METHODIST в incident_add)
app/children.py                          (_can_edit_incident, _category_label,
                                          INCIDENT_CATEGORY_LEGACY, пагинация registry,
                                          can_edit_rows для methodist)
app/core/context_processors.py           (incident_category_label)
app/templates/incidents_my.html          (+ Новый, per-row _row_editable, Sort dropdown
                                          table+list+kanban, data-occurred,
                                          CSS .sort-dropdown)
app/templates/incidents_registry.html    (per-row counter, pagination nav,
                                          Sort dropdown, data-occurred, CSS)
app/templates/incidents_dashboard.html   (incident_category_label)
```

**Smoke (admin / test_methodist / test_social, локально :5001):** все 200, METHODIST видит «+ Новый» и `bi-eye` на чужих, категория `conflict` рендерится как «Драка/конфликт», 6 sort-row × 2 стрелки в каждом меню.

**Не сделано:** деплой накопленного s67-s76 (`deploy_session67_76.py` paramiko + .bak + smoke). Сверка с продом перед заливкой шаблонов — обязательна (`feedback_deploy_over_prod.md`).

См. `../memory/project_session76_methodist_p2_sort.md`.

## Сессия 75 (26.04.2026) — SP-clarity (Назначено мне) + UX — ОТКАЧЕНА в s76, НЕ ЗАДЕПЛОЕНО

Поверх s74 (`f5c8912`). 3 файла, без миграции БД. Сессия закрыта на паузе —
директор смотрит локально, по фидбэку часть визуальных решений откатили
(см. `feedback_no_visual_overload.md`).

**Контекст:** SP жаловался «при ADMIN-доступе всё было понятно, а сейчас нет».
Решение: SP = почти ADMIN, но с явной видимостью «что назначено на меня».

**Что сделано:**
- **Backend `incidents_my()`** — убрана 4-я вкладка «Назначенные мне» для SP,
  фильтр `?assignee=me` (assignee_id ИЛИ author_id == uid), метрики
  `sp_mine_count` (открытые мои+автор) и `sp_mine_overdue` (мои с Task
  status=«Просрочена»). `can_edit_rows=True` для SP во всех видах.
- **SP-плашка** `bi-bookmark-fill «Назначено на меня: N · K просрочено · [Только мои]»`
  сверху `/incidents/my` (видна только SP). Цвета — нейтральные системные
  (`#fff/#e9ecef/#495057`), при активном фильтре кнопка `#283149`.
- **Status-subtabs scope-блок «Все по школе ↔ Назначенные мне»** для SP
  удалён.
- **Kanban-сортировка «мои сверху»** в каждой колонке для SP (стабильная
  внутри подгрупп, без изменения серверного порядка).
- **Tooltip на чужих kb-card** для SP: «Назначен другому пользователю —
  изменения недоступны».
- **Кнопка «✓ Я отработал»** в kb-card (раньше только в table/list/user-card)
  для SP на «своих» (assignee==me) и не closed/resolved.
- **Иконки даты разграничены:** `bi-calendar-event` + tooltip «Дата инцидента
  (когда произошло)» в Доске и Списке (раньше эмодзи 📅 без tooltip).
- **Tooltip на чужих edit/delete в `/registry`** для SP — иконки видны но
  disabled с `title="Только свои инциденты — назначенные на вас или
  созданные вами"`.
- **Подписи Filter/Group/Свойства** на ≥768px (`d-none d-md-inline`).
- **Точка-индикатор** у Свойств (если что-то скрыто) и у Группировки
  (если активна) в `/my` и `/registry`.

**Откат после фидбэка директора (по `feedback_no_visual_overload.md`):**
- Удалена оранжевая рамка `.kb-card.mine` (border:#fb923c) — «выделять рамкой не надо».
- Удалено приглушение `.kb-card.not-mine{opacity:.6}` — «приглушать остальные не надо».
- Удалён значок 👤 в углу `.kb-card.mine::after`.
- Удалены `tr.row-mine` и `.inc-list-item.mine` (полоски слева).
- Перекрашена плашка из оранжевых тонов в нейтральные.
- Эмодзи 📌 заменено на `bi-bookmark-fill` (эмодзи перекрашиваются ОС).

**Итог визуального выделения «моих»:** только сортировка в Доске +
плашка-счётчик сверху + tooltip при наведении на чужие. Никаких рамок/
полосок/приглушений на самих карточках/строках.

**Файлы (3):**
```
app/children.py                          (SP-метрики, ?assignee=me, без mine-tab)
app/templates/incidents_my.html          (плашка, kanban-сортировка, mark-resolved
                                          в Доске, calendar-event иконка, dot-индикаторы)
app/templates/incidents_registry.html    (disabled tooltip для SP, dot-индикаторы)
```

**Smoke (test_social/test123, локально :5001):**
- `/incidents/my[?view=kanban|list][&assignee=me]` 200, плашка/счётчик/toggle/
  bi-calendar-event/«Я отработал»/tooltip — все маркеры на месте.
- `/incidents/registry` 200 для SP, disabled-кнопки на чужих с tooltip.
- py_compile OK. Хук `py_syntax_check` падает на кириллице в пути — игнорировали.

**Открытые вопросы для s76:**
1. Что именно «оранжевая рамка в задачах» в фидбэке директора —
   не конкретизировано.
2. Нужно ли вообще выделение «моих» или ограничиться плашкой+сортировкой.
3. Деплой накопленного s67-s75 — после правок директора по фидбэку.

См. `../memory/project_session75_sp_clarity.md` — детали.

## Сессия 74 (26.04.2026) — P1+P2 после аудита s73 — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

Поверх s73 (`1ab82ba`). 7 файлов, без миграции БД. Делается перед общим
деплоем накопленного s67-s74.

**P1 (5 правок из решений директора):**
1. **METHODIST UI hide** в `/incidents/my`: кнопка «+ Новый инцидент» скрыта;
   иконка `bi-pencil` → `bi-eye` (title «Просмотр») когда `can_edit_rows=False`
   (закрывает и SP в общих вкладках). Backend-гард `_can_edit_incident` уже жёсткий.
2. **SP edit/delete-иконки в `/incidents/registry`**: условие в шаблоне расширено
   на `is_social_pedagog` (новая переменная из роута). В /my эти иконки
   у SP уже были — приведено в соответствие.
3. **Filter popup на <480px** — превращается в bottom-sheet (fixed, full-width,
   border-radius сверху, max-h:85vh, overflow-y:auto). Селектор `.filter-popup`
   общий для my/registry/dashboard. Правило в `incidents-status.css`.
4. **Кнопка «Свойства» на <768px** — текст обёрнут в `<span class="d-none d-md-inline">`,
   остаётся только иконка `bi-eye`. 4 места (registry, dashboard, kanban+table в my).
5. **Backend dedup `incident_set_status`** — второе уведомление пропускается,
   если `inc.assignee_id == inc.author_id` (раньше при author==assignee≠actor
   уходило 2 одинаковых).

**P2 (5 правок поверх P1):**
- **Excel-экспорт `/incidents/registry/export`** теперь принимает `?status=`
  (включая meta-`open`) и `?hide_cols=col-cat,col-desc,...` (whitelist 8 столбцов
  + автоснятие префикса `col-`). `export_url` в шаблоне уже шлёт hide_cols через JS.
- **`SavedView.qs` валидация** — `_normalize_qs()` через whitelist 10 ключей
  (`view, tab, status, group_by, category, class_id, grade, q, sort, page`),
  max 1000б qs / 200б на значение. Защита от мусора и случайных секретов в URL.
- **Дашборд → popup-фильтры** — карточка `.incident-panel` с формой убрана,
  её содержимое перенесено в popup рядом с кнопкой «Свойства» (та же воронка
  `bi-funnel` + точка-индикатор активного фильтра). CSS `.filter-popup`
  продублирован в шаблоне (был только в incidents_my/registry).
- **Локализация category-кодов** — N/A: `INCIDENT_CATEGORIES` уже хранятся как
  русские строки, кодов нет.
- **Мобильный auto-list-view <768px** — на `/incidents/my` если в URL нет `?view=`
  и в localStorage нет `my_inc_view` — на узких экранах один безопасный редирект
  на `?view=list`. Явный выбор пользователя приоритетнее. В /registry list-view
  убран в s72, не применимо.
- **`sort=status` по `STATUS_ORDER`** — через `sqlalchemy.case` (был алфавит кода).

**P2-3/P2-4 из аудита НЕ трогали** — group_by после пагинации сознательно
(Notion-style); GET `/edit` для read-only ролей закрыт через `fieldset disabled`
(s64 #12) — не баг.

**Файлы (7):**
```
app/children.py                          (+is_social_pedagog в registry, dedup,
                                          export hide_cols+status, sort=status case)
app/saved_views.py                       (_normalize_qs whitelist)
app/static/css/incidents-status.css      (@media <480px filter-popup bottom-sheet)
app/templates/layout.html                (?v=20260426 для css)
app/templates/incidents_my.html          (METHODIST hide, eye-vs-pencil,
                                          d-none d-md-inline на «Свойства»,
                                          mobile auto-list-view)
app/templates/incidents_registry.html    (SP icons, d-none d-md-inline)
app/templates/incidents_dashboard.html   (filter-popup CSS+JS+форма,
                                          d-none d-md-inline, удалена .incident-panel)
```

**py_compile + jinja-parse — OK.** Сервер поднимали локально на :5001 для визуального
ревью. Хук `py_syntax_check.py` падает на кириллице в пути — игнорировали
(правило `feedback_hook_false_positive.md`), сверка через py_compile.

**Что в следующей сессии (s75):** ещё несколько правок (директор смотрит локально),
после — `deploy_session67_74.py` (paramiko + .bak_session67_74 + рестарт + smoke).
Перед заливкой шаблонов сверять с продом (правило `feedback_deploy_over_prod.md`).

## Сессия 73 (26.04.2026) — Аудит тремя агентами — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

Master fast-forward на `b9baaea` (41 коммит s62-s72 поверх продового `d5cccdf`/s60b).
Три параллельных read-only-агента (ui-ux + backend + regression).
Артефакты: `.audit_s73/{ui-ux,backend,regression}/REPORT.md` (UI/UX — только в чате,
скриншоты в `.audit_s73/ui-ux/*.png`).

**Итог: P0 нет.** Деплой s67-s72 готов после P1-фиксов в s74.

**P1 на s74 (решения директора):**
1. METHODIST: скрыть «+ Новый инцидент» и заменить карандаш→глаз в `/incidents/my`.
   Backend-гард `_can_edit_incident` уже жёсткий, UI пускает на форму — закрыть.
2. SP в `/incidents/registry`: добавить edit/delete-иконки + tooltip
   (в /my есть, в /registry — нет).
3. Filter popup на <480px уезжает за левый край → full-screen offcanvas.
4. Кнопка «Свойства» на <768px обрезается → иконки без подписей.
5. Backend: `incident_set_status` шлёт 2 уведомления если author == assignee != actor.

**P2 — после деплоя:** Excel-экспорт `?hide_cols=`/`?status=`, SavedView.qs валидация,
дашборд → popup-фильтры, локализация category-кодов, мобильный auto-list-view.

**Миграции к деплою — не нужны** (regression подтвердил): saved_view через
`db.create_all()`, индексы s63b через `CREATE INDEX IF NOT EXISTS` в `bootstrap.py`.

## Сессия 72 (26.04.2026) — Чистка инцидентов — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

Поверх s71. Коммиты `0484663` + `914bc80` + `b2d615e` на `feature/kubok-school`.
Реализованы 5 пунктов плана `project_session72_plan.md` + дашборд:

- **`/incidents/registry`** — убран view-switcher table/list, оставлена одна
  таблица. Шаблон полностью переписан. Col-picker «Свойства» → планируется
  использовать как фильтр Excel-экспорта (UI готов, backend не подхватывает).
- **`/incidents/dashboard-legacy`** — убран list view, кнопка «Свойства»
  с иконкой `bi-eye`.
- **`/incidents/my`** — status-subtabs убраны во всех 3 видах для ADMIN/DEPUTY.
  SOCIAL_PEDAGOG получает переключатель «Все по школе ↔ Назначенные мне»
  (это scope, не статус — без него SP не может вернуться в режим «только свои»).
- **Backend `incidents_my`** (`children.py:4408`) — для view=table/list игнорим
  `STATUS_BUCKETS[active_tab]`, отдаём все статусы. Параметр `?status=`
  для точечного фильтра. Kanban — без изменений.
- **Фильтры → popup** — кнопка-воронка `bi-funnel` рядом с группировкой,
  точка-индикатор при активном фильтре. Применяется в /my, /registry, kanban.
- **Бесшовная группировка** — клик опции Group → JS перегруппировывает
  отрендеренные `<tr data-row="1">` / `.inc-list-item` через data-attrs
  (`data-category`, `data-class`, `data-class-id`, `data-building`,
  `data-assignee-id`, `data-assignee-label`, `data-status`). URL обновляется
  через `history.replaceState`. Collapse-state в localStorage.
- **Named views inline** — dropdown «+ Создать вид» (с типами) и кнопка
  «💾 Сохранить» удалены. Одна кнопка `nvCreateBtn`: клик → inline-input
  «Название вида…», Enter → POST `/api/saved-views` с qs текущих фильтров +
  `view=<текущий>`. Esc/blur → отмена. `savedViewModal` удалён в обоих шаблонах.

**Файлы (4):**
```
app/children.py                          (+10 строк)
app/templates/incidents_dashboard.html   (-118 строк)
app/templates/incidents_registry.html    (полностью переписан)
app/templates/incidents_my.html          (точечно + JS regroup)
```

**Smoke (admin/admin123, локально :5001, 13 closed + 5 in_progress + 13 new):**
- `/my?view=table` → все 31, `?status=closed` → 13, `?group_by=status` → 3 группы.
- `/my?view=kanban` — без status-subtabs.
- `/registry`, `/dashboard-legacy` — без list view.

**Хвосты для s73:** Excel-экспорт `?hide_cols=`, деплой накопленного s67-s72.

См. `../memory/project_session72_done.md`.

## Сессия 71 (26.04.2026) — Group by + collapse групп — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

Поверх s70. Базовая инфраструктура группировки в `/incidents/my` и `/incidents/registry` для table+list. 3 файла, без миграции БД.

- **Backend `_group_incident_rows(rows, group_by, status_labels)`** в `app/children.py:3475` — Python-группировка построенных рядов (после пагинации, в пределах текущей страницы). Ключи: `category | class | building | assignee | status`. Возвращает `[{key, label, rows}]` в порядке первого появления.
- **`incidents_my` route** — читает `?group_by=` (whitelist `_GROUP_BY_KEYS`), на kanban игнорируется, на table/list передаёт `groups`/`f_group_by` в шаблон.
- **`incidents_registry` route** — то же самое (groups для общей таблицы и списка, JS view-switcher не трогаем).
- **Шаблон incidents_my.html** — рядом с кнопкой «Свойства» добавлен Group dropdown (`bi-collection`, 6 опций: «Без группировки» + 5 свойств). На table рендерится `<tr class="group-header" data-group-key>` через `colspan`, на list — `<div class="inc-list-group-header">` + `<div class="inc-list-group-body">`.
- **Шаблон incidents_registry.html** — то же самое (Group dropdown рядом с col-picker, group-headers в обоих видах).
- **JS collapse + localStorage** — клик на header сворачивает группу, состояние в `localStorage['incidents_my_collapsed_v1::<group_by>']` (отдельный ключ для registry). Каретка ▾ → ▸. Без AJAX — только клиент-side toggle.

**Файлы (3):**
```
app/children.py                         (_group_incident_rows + 2 route)
app/templates/incidents_my.html         (CSS + Group dropdown + group-headers + collapse JS)
app/templates/incidents_registry.html   (CSS + Group dropdown + group-headers + collapse JS)
```

**Smoke (admin/admin123, локально :5001):**
- `/incidents/my` (без группы) → 200, 0 rendered group-header
- `/incidents/my?group_by=category` → 200, group-header rendered
- `/incidents/my?view=list&group_by=class` → 200, list-group-header + list-group-body
- `/incidents/my?view=kanban&group_by=category` → 200, group_by игнорируется (34 kb-draggable)
- `/incidents/registry?group_by=building` → 200, 7 групп rendered

**Что отложено в s72** (по фидбэку пользователя в конце s71):
- Реестр: убрать view-switcher (table/list) → один чистый список с гибким col-picker для просмотра+экспорта.
- `/incidents/my` table+list: убрать status-subtabs «Входящие/В работе/Завершённые» (в kanban оставить — там это колонки).
- Фильтры → popup рядом с группировкой (как dropdown), убрать сверху.
- Бесшовное переключение группировки без reload (DOM-перегруппировка JS-ом).
- Named views UX: «+ Создать вид» сразу делает inline-новую вкладку, без dropdown-выбора типа и отдельной кнопки «Сохранить».

См. `../memory/project_session71_group_by.md` и `project_session72_plan.md`.

## Сессия 70 (26.04.2026) — D&D fix + bootstrap.js→head + реверс flow «Сохранить вид» — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

Поверх s69. Промежуточная сессия перед большой s71. 3 файла, без миграции БД.

- **D&D в kanban не работал** — внутри `.kb-card` стояли `<a>`, нативно draggable, перехватывали drag. Фикс: `draggable="false"` на `<a>` к incident_edit и child_card в `incidents_my.html:569-582`. Карточка остаётся draggable.
- **SP может двигать свои + назначенные** — в `_can_pick` добавил `r.inc.author_id == current_user_id` (было только assignee_id). Админ/DEPUTY двигают всё.
- **Bootstrap is not defined** (4 console errors) — `bootstrap.bundle.min.js` стоял в КОНЦЕ body, inline-IIFE с `new bootstrap.Modal(...)` падали. Перенёс в `<head>` сразу после bootstrap-icons CSS. layout.html:13.
- **Реверс flow «Сохранить вид»** — в `/incidents/my` и `/incidents/registry`:
  - Раньше: одна кнопка → модалка с radio «Тип отображения» + имя → сохранение.
  - Теперь: dropdown «+ Создать вид» (3 опции: Таблица/Доска/Список — клик ведёт на ?view=<тип>) + отдельная оранжевая кнопка «💾 Сохранить» → упрощённая модалка только с полем «Имя», тип берётся автоматом из view_mode.
  - В registry — без kanban-опции (только Table/List).

**Файлы (3):**
```
app/templates/layout.html               (bootstrap.js → в <head>)
app/templates/incidents_my.html         (D&D draggable=false, _can_pick + author, dropdown nvCreateBtn, упрощённая модалка)
app/templates/incidents_registry.html   (dropdown nvCreateBtn Table/List, упрощённая модалка)
```

**Smoke (admin/admin123, локально :5001):** /incidents/my?view=kanban — 0 console errors (было 4), D&D через DragEvent работает (incoming→in_work, статус new→in_progress, AJAX 200, pill обновился). Save modal: name+POST /api/saved-views 200 с qs=view=table.

**Отложено в s71** (пункты 4/5/6 пользователя — большая работа ~3-4 часа):
- View settings панель (Notion-style шестерёнка) для всех 3 видов с табами Filter/Sort/Group/Properties/Collapse.
- Group/Sort по любому свойству (категория/класс/здание/исполнитель/статус) + новый ?group_by= в backend.
- Свёртка групп с persistence в localStorage.

См. `../memory/project_session70_dnd_view_flow.md`.

## Сессия 69 (26.04.2026) — D&D в kanban + property visibility + SavedView modal — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

Поверх s68 (966f8e9). Пункты 1/2/3 из плана по скринам Notion (отзыв пользователя).
Будут правки в s70 (пункты 4/5/6: Notion-панель View settings, Group/Sort по свойству, свёртка групп).
2 файла, без миграции БД.

- **D&D в kanban** на `/incidents/my?view=kanban`. Нативный HTML5 DnD.
  `.kb-card.kb-draggable` (если `_can_pick`), drop-zone `.kb-col-body[data-bucket]`.
  POST `/incidents/<id>/set-status` с дефолтом бакета: `incoming→new`, `in_work→in_progress`,
  `completed→closed`. Оптимистичный UI, на ошибке откат + alert. Счётчики и status-pill/badge
  обновляются в DOM.
- **Property visibility + переименование «Колонки → Свойства»**. В kanban-режиме
  col-picker заменён на `kb-prop-toggle` (6 свойств: kp-cat/kp-students/kp-date/
  kp-assignee/kp-tasks/kp-status), скрытие через `.inc-kanban.hide-kp-*`,
  persistence в localStorage `kanban_my_props_v1`. В table/list лейбл переименован,
  иконка `bi-eye`. То же в `incidents_registry.html`.
- **SavedView modal** вместо `prompt()`. `#savedViewModal` с input «Название» +
  radio-группа «Тип отображения» (Текущий/Таблица/Доска/Список — registry без Доски).
  При сохранении в qs дописывается `view=...` если выбран не «текущий». Логика
  `/api/saved-views` без изменений. Лимит 12, ошибки в `#svError`.

**Файлы (2):**
```
app/templates/incidents_my.html
app/templates/incidents_registry.html
```

**Smoke (admin/admin123, локально :5001):**
- `/incidents/my[?view=table|kanban|list]` 200, `/incidents/registry[?view=list]` 200
- `POST /incidents/<id>/set-status` (kanban-D&D) 200 `{ok:true,status:in_progress}`
- HTML содержит `kb-draggable`, `data-bucket=incoming/in_work/completed`, `kb-prop-toggle`,
  `STATUS_LABEL`, `BUCKET_TO_STATUS`, `savedViewModal`, `svView` — всё на месте.

См. `../memory/project_session69_kanban_dnd.md`.

## Сессия 68 (25.04.2026) — Notion-вид: kanban + named views + редизайн layout — ЛОКАЛЬНО, НЕ КОММИТ

Большая Notion-сессия для `/incidents/my` и `/incidents/registry`. Поверх с-67 (8ef2aac).
**НЕ закоммичено** — пользователь хочет внести правки в следующей сессии перед commit.
9 файлов (3 шаблона + children.py + 2 новых модели/blueprint).

**Ключевое:**
- **Kanban-доска** на `/incidents/my` (admin-view) — 3 колонки по статус-бакетам, inline-смена статуса
  через AJAX `/incidents/<id>/set-status`. SOCIAL_PEDAGOG: picker только на инцидентах где он назначен.
- **Rollup-плашка задач** в карточке инцидента — Notion-стиль (progress-bar «N из M закрыто»,
  плашка просроченных, цветные точки по группам статуса).
- **Named views в БД** — новая модель `SavedView (user_id, scope, name, qs)`, AJAX-эндпоинты
  `/api/saved-views` (GET/POST/DELETE), переносится между устройствами. Лимит 12 на scope.
  Без миграции — `db.create_all()` создаёт таблицу. На проде PG подхватит при старте.
- **Редизайн layout `/incidents/my`:** крупные view-tabs сверху (📋 Таблица · ⊞ Доска · ☰ Список + named views),
  status-tabs (Входящие/В работе/Завершённые) переехали ниже под фильтры, видны только в Table/List.
  В Kanban статусы — это сами колонки.
- **Редизайн `/incidents/registry`:** те же крупные view-tabs (Таблица/Список, без Доски и status-tabs).
  Старые мелкие view-btn у таблицы убраны (дубль).
- **Дашборд `/incidents/dashboard-legacy`:** status-picker → статичные `<span class="status-badge">`.
  Решение: дашборд — общая картина для обзора, менять статус → в Реестре или /my.

**Файлы для деплоя (9):**
```
app/children.py                         (kanban_groups + task_counts)
app/models/__init__.py                  (+from .saved_view import *)
app/models/saved_view.py                (новый)
app/modules/__init__.py                 (+saved_views_bp)
app/saved_views.py                      (новый, AJAX endpoints)
app/templates/incident_edit.html        (rollup-плашка задач)
app/templates/incidents_my.html         (view-tabs + kanban + status-subtabs + named views fetch)
app/templates/incidents_registry.html   (view-tabs + named views fetch, kanban убран)
app/templates/incidents_dashboard.html  (статичные бейджи)
```

Без миграции БД (только `db.create_all()` для `saved_view`). Деплой — после правок в s69.

**Smoke (admin/social/teacher, локально :5001):** все страницы 200, kanban работает,
SP видит picker только на своих инцидентах, teacher видит старую user-view нетронутой,
дашборд без picker (только бейджи), CRUD `/api/saved-views` работает.

См. `../memory/project_session68_notion_kanban.md` — детали и smoke-таблица.

## Сессия 65 (25.04.2026) — копирайтинг + мобильная v3 + a11y ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

P3-косметика поверх с-64 (08a74dc). Коммит `77ae8a5` на `feature/kubok-school`.
6 шаблонов, без миграций. Деплой одним пакетом s62+s63b+s64+s65 после аудита прода.

**Копирайтинг (13 строк):** «— все —»→«Все», «— выбрать —»→«Выберите категорию/класс»,
«— не назначен —»→«Без исполнителя», «Кратко опишите ситуацию»→«Что произошло? Кто
участвовал, где, когда (если важно)», «Полная история»→«История изменений»,
«Прочитать»→«Прочитать всё» в колокольчике, «Новые · назначенные · в работе»→«Новые
+ назначенные + в работе», «Кубок школы класса X»→«Кубок школы — X»,
«Инцидентов пока нет.»→«За выбранный период инцидентов нет — это хороший день.»

**Мобильная v3 (4/6):** row g-2→g-2 g-md-3 в фильтр-барах; stats-strip-value
2rem→1.4rem на <576px; assignee-menu position:fixed left/right:1rem на <576px;
modal-fullscreen-sm-down на 7 модалках. **Пропущено:** Hero «...» меню и
авто-list-view <768px (оба требуют переписывания JS, риск регрессии).

**A11y C1 (status-pill):** aria-haspopup="listbox", aria-expanded, aria-label на
кнопке; role="listbox" на меню; role="option" tabindex="-1" на опциях. JS
синхронизирует aria-expanded при open/close (вкл. клик-вне и закрытие соседнего).

**A11y C2 (колокольчик):** bell-filter-menu role="menu"+aria-label, опции
role="menuitemradio"+aria-checked sync в applyFilter. aria-expanded toggle на
bell-filter-btn. :focus-visible оранжевый outline 2px. Focus-trap не делал.

**Smoke (admin/admin123, :5001):** /incidents/dashboard-legacy, /registry, /my,
/new, /31/edit, /31/timeline — все 200. Все aria и copy-замены подтверждены grep
по rendered HTML.

**Файлы (6):** `app/templates/{incident_edit,incident_new,incidents_dashboard,incidents_my,incidents_registry,layout}.html`.
Перед деплоем — сверка с продом (правило `feedback_deploy_over_prod.md`).

**C3** (вынести incidents.css) — отложен (рефакторинг ≠ хирургическая правка).

## Сессия 64 (25.04.2026) — P1-хвосты + P2 ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

P1-хвосты (#12, #15) + P2 (B3-B7 UI, #5/#9/#11/#14/#21 бэкенд) поверх с-63. Сделано на ветке `feature/kubok-school` поверх коммита `3ec9f6c`. 6 файлов, без миграции БД.

**P1-хвосты (2):**
- **#15 `?view=` URL + запоминание** — без миграции (User.preferences не нужен): localStorage + URL через `history.replaceState`. В `incidents_registry.html` и `incidents_dashboard.html` — клик пишет в URL и localStorage; на загрузке URL > localStorage > 'table'. В `incidents_my.html` (server-rendered switcher через `?view=`) — клик пишет в localStorage; при заходе без `?view=` если localStorage='list' → один безопасный редирект на `?view=list`.
- **#12 read-only `/incidents/<id>`** — без отдельного роута. В `incident_edit.html` поля формы обёрнуты в `<fieldset {% if not can_edit_incident %}disabled{% endif %}>`. Заголовок переключается «Изменить инцидент» ↔ «Карточка инцидента». Кнопка «Я отработал» (assignee) и timeline-ссылка — снаружи fieldset, остаются активными. Подтверждено: PSYCHOLOGIST-роль видит read-only вид.

**P2 UI (B3-B7):**
- **B3** — убран chip-бейдж «Инциденты · реестр»/«…дашборд» дублирующий H2 в `incidents_registry.html` и `incidents_dashboard.html`. CSS-класс `incident-chip` оставлен на случай переиспользования.
- **B4** — все 6 inline `onclick="this.parentElement.style.display=…"` desc-toggle в 3 шаблонах заменены на `class="js-desc-expand"`/`js-desc-collapse` + по одному document-делегату через `closest()`.
- **B5** — на дашборде рядом с «Динамика за 7 дней»: `▲ N% к прошлой неделе (M)` (красным) или `▼ N%` (зелёным) или «Без изменений». Backend в `incidents_dashboard_legacy()` считает `prev_week_total` тем же `base`-фильтром (учитывает grade/class/category/status). При `prev_week_total=0` подпись «Нет данных за прошлую неделю». Шаблон передаёт `week_total`, `prev_week_total`, `week_delta_pct`.
- **B6** — live-фильтр в `/incidents/registry`: select-ы submit-ятся при `change`, инпут ФИО — debounce 350мс. Кнопки «Применить»/«Сброс» оставлены как fallback.
- **B7** — `<select multiple>` в `incident_new.html` заменён на picker: scroll-area max-height 240px с чекбоксами + поле «Поиск по ФИО…» (фильтрует по `data-search`). `name="child_ids"` сохранён как у old-select — backend (`request.form.getlist("child_ids")`) не менялся. JS: `loadChildren(classId, picker, selectedChildIds)` рендерит `<label><input type="checkbox" name="child_ids" value="{id}">FIO</label>`. Submit-валидация на `input[name="child_ids"]:checked.length === 0`.

**P2 бэкенд (5):**
- **#5 race на set-status** — `incident_set_status` и `incident_set_assignee` теперь через `Incident.query.filter_by(id=...).with_for_update().first()`. На PG берёт row-lock, на SQLite молча no-op. Если строка не найдена — `abort(404)`.
- **#9 дубль логики назначения** — извлечён helper `_apply_assignee_change(inc, new_assignee_id, note_text)` в `app/children.py:3362` (рядом с `_auto_create_task_for_incident`). Логика: change assignee, лог `IncidentAssignment`, заметка `[Назначение]`, авто-Task для PSY/SOC/METH, автопереход new↔assigned. Используется и в `incident_edit` (форма), и в `incident_set_assignee` (AJAX). Дубль ~30 строк удалён в обоих местах.
- **#11 двойное уведомление автор=assignee** — внутри helper'а уведомления НЕ отправляются `actor_id` (`new_assignee_id != actor_id` для assignee, `inc.author_id != actor_id` для автора). Smoke-тест с очисткой `incident_notification` подтвердил: admin сам себе → 0 уведомлений.
- **#14 orphan-файлы при rollback** — в `_save_incident_note_attachments` теперь собираем `written_paths`; при exception на середине цикла удаляем уже сохранённые физические файлы (`os.remove`) перед re-raise. Транзакцию БД откатывает вызывающий (как раньше).
- **#21 жёсткий limit(500)** — в `incidents_my` admin-view расширили до 1000 + флаг `rows_limit_reached` + UI-предупреждение «· достигнут потолок 1000» в шапке таблицы (красным). Полная пагинация — отдельной сессии.

**Пропущено сознательно:**
- **#7 глобальный кэш ФИО** — нет конкретной метрики/места где он бьёт по перфу; риск регрессии без замера. Имеет смысл когда покажет себя в profiler — отдельной сессией.

**Smoke (admin/admin123, локально :5001):**
- `/incidents/dashboard-legacy[?view=list]`, `/incidents/registry[?view=list][?status=open]`, `/incidents/my[?view=list]`, `/incidents/new`, `/incidents/31/edit`, `/timeline` — все 200.
- `/incidents/new` — `child-picker` div и `childPickerSearch` input на месте, старый `<select multiple>` ушёл.
- `/incidents/31/edit` — `<fieldset` присутствует, заголовок «Изменить инцидент»/«Карточка инцидента» переключается через `can_edit_incident`.
- POST `/incidents/31/set-status` (in_progress→assigned) → 200 `{ok:true,status:assigned}`.
- POST `/incidents/31/set-assignee` (admin→admin) → 200, **0 self-notifications** в `incident_notification`.
- POST `/incidents/31/set-assignee` (unset) → 200, статус автоматом → `new`.
- Дашборд: блок `▲/▼ к прошлой неделе` отрисован.

**Файлы для деплоя (6):**
```
app/children.py
app/templates/incident_edit.html
app/templates/incident_new.html
app/templates/incidents_dashboard.html
app/templates/incidents_my.html
app/templates/incidents_registry.html
```
Перед деплоем — сверять с продом (правило `feedback_deploy_over_prod.md`). Без миграций БД, без новых ALTER TABLE. На прод деплой s62+s63b+s64 одним пакетом, когда дойдут руки до школьного WiFi.

**Хук `py_syntax_check.py`** во время сессии повторно падал с `[Errno 2]` на кириллице в пути — игнорировался, py_compile сверка после каждой правки давала `OK` (правило `feedback_hook_false_positive.md`).

## Сессия 63 (25.04.2026) — шаг b (P1) ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО

9 P1-правок поверх c-62 на основе единого плана `incident_547/_session62_unified_plan.md`. Перед стартом s61-черновик стэшнут (`stash@{0}` "s61 draft на паузе (перед b)"). Деплой-скрипт ещё не написан.

**Бэкенд (3):**
- `app/bootstrap.py`, `app/models_legacy.py` — 8 индексов на инциденты: `Incident.{status, assignee_id, author_id, occurred_at, category}` + `IncidentNote.{incident_id, author_id}` + композит `(status, occurred_at DESC)`. `index=True` в моделях + `CREATE INDEX IF NOT EXISTS` в `ensure_runtime_schema()` (PG-совместимо).
- `app/children.py:4271` — N+1 в `/incidents/my` user-view: `IncidentNote.query...first()` в цикле → один `IN`-запрос с `joinedload(IncidentNote.author)` + group-by-incident pick.
- `app/children.py:4092` — `incidents_registry()` понимает meta-значение `?status=open` как `Incident.status IN (new, assigned, in_progress)`.

**UI (5):**
- `incidents_my.html:149` — `view-btn.active` `#283149`→`#ff7043` (унифицировано с registry/dashboard/social_passport).
- `incidents_dashboard.html` — KPI «Открытые сейчас» обёрнут в `<a class="stats-strip-item-link">` → `/incidents/registry?status=open`. CSS hover-стиль: оранжевая подсветка значения.
- 3 шаблона (registry/dashboard/my, table+list × 3 = 6 кнопок) — кнопка «Удалить» теперь `btn-outline-danger js-incident-delete-btn` (`type="button"`), `onsubmit="return confirm()"` снят. data-attrs `data-category` + `data-kids` (`r.children|map('fio')|join`).
- В каждом из 3 шаблонов под `{% endblock %}` — bootstrap-модалка `#incidentDeleteModal` (заголовок «Удалить инцидент?», категория + ФИО, btn-danger «Удалить») + JS-делегат через `document.addEventListener('click')` на `.js-incident-delete-btn` → `pendingForm.submit()`. Bootstrap 5.3.3 уже глобально в `layout.html`.
- `incident_timeline.html`, `incident_new.html` — хлебные крошки разные для admin/user через `can('incident_registry_view')`: admin → «Реестр инцидентов»/«Дашборд инцидентов», user → «Мои заявки». Кнопка «Назад» в timeline — «Назад в реестр» / «Назад в Мои заявки».

**Notion-связки (2, без миграции БД):**
- `app/models/tasks.py` — `Task.incident = relationship('Incident', backref='tasks', order_by=Task.created_at.desc())`. `Task.child` теперь с `backref('tasks', lazy='dynamic')`.
- `app/children.py:3624` `incident_edit` — `related_tasks = list(inc.tasks)` (заменил самописный `Task.query.filter(...)`). UI-блок «Связанные задачи» уже был в `incident_edit.html:192` с с-42.
- `app/templates/child_card.html` — после блока ШСК добавлена сворачиваемая плашка «Поручения по ученику» (показывается, только если `_open_tasks` не пуст). Топ-10 открытых задач, `child_task_stats.overdue` подсвечен красным. Переменные `child_tasks`/`child_task_stats` уже передавались с роута, но в шаблоне не использовались.

**Smoke (admin/admin123, локально на :5001):** `/incidents/dashboard-legacy`, `/incidents/registry`, `/incidents/registry?status=open`, `/incidents/my`, `/incidents/new`, `/incidents/<id>/edit|timeline`, `/children/9` — все 200. Сервер останавливался через `Stop-Process` по pid из `Get-NetTCPConnection -LocalPort 5001`.

**Что НЕ делали (отложено):** #12 read-only `/incidents/<id>` (L), #15 `?view=` в `User.preferences`, все P2/P3 пункты, миграции `01/03/04` (cascades, MAX-fields, profile-fields), MAX-бот, единый `/profile/settings`.

**Файлы для деплоя (10):** `app/bootstrap.py`, `app/children.py`, `app/models_legacy.py`, `app/models/tasks.py`, `app/templates/{incidents_my,incidents_registry,incidents_dashboard,incident_timeline,incident_new,child_card}.html`. Деплой — отдельной сессией. Перед заливкой шаблонов сверять с продом (правило `feedback_deploy_over_prod.md`).

**s61 черновик** — в `git stash` (`stash@{0}`), 8 файлов на ветке `feature/kubok-school`. Не трогаем без отдельного запроса.

## Сессия 62 (25.04.2026) — ЛОКАЛЬНО, НЕ ЗАДЕПЛОЕНО (деплой в понедельник 27.04)

Параллельный аудит трёх ролей через worktree в копии-зама (`school_tracker_copy/.claude/worktrees/{ui-ux,backend-audit,notion-redesign}`). Сведено в `incident_547/_session62_unified_plan.md`. Внедрены только 3 P0 правки. Деплой отложен — пользователь не на школьном WiFi. Коммит `9c15b80` на `feature/kubok-school`.

**P0 #1 — `app/children.py:3665` `incident_delete` cascade.** На Postgres падало `IntegrityError` из-за orphan-FK в `IncidentNotification` и `Task.incident_id` (без cascade/ondelete). На SQLite не воспроизводилось. Минимальный фикс — 4 строки: `IncidentNotification.query.filter_by(incident_id=inc.id).delete()` + `Task.query.filter_by(incident_id=inc.id).update({"incident_id": None})` до `db.session.delete(inc)`. Миграции БД (cascade на FK) — отдельной сессией.

**P0 #2 — `incidents_registry.html` / `incidents_dashboard.html` цвета 2 пропавших статусов.** Добавлены CSS для `s-assigned` (амбер `#fef3c7`/`#92400e`, dot `#f59e0b`) и `s-resolved` (фиолет `#f3e8ff`/`#6b21a8`, dot `#a855f7`) в `status-badge`, `status-pill`, `sp-dot`, `sp-pill`. До правки 2 из 5 статусов в реестре и дашборде рендерились без цвета. Эталон — `incidents_my.html`.

**P0 #3 — `incident_new.html` мёртвый JS.** Удалено 78 строк JS, обращавшихся к несуществующим ID (`#timePicker5`, `#hourSelect`, `#minuteSelect`, `#occurred_time`). Бросало `Cannot read properties of null` на каждом открытии формы.

**Артефакты для следующей сессии (b):** см. `../memory/project_session62_audit_artifacts.md`. В worktree-ветках лежат: `tmp/ui_ux_audit.md` (16 пунктов), `tmp/backend_issues.md` (24 проблемы + MAX 60% + /profile/settings проектирование), `tmp/migrations_drafts/01-04` (4 миграции-черновика, не запускались), `tmp/notion_redesign_proposal.md` + `tmp/mockups/incidents_kanban.html`. Главный инсайт Notion: в личном Notion пользователя уже работает `Tasks↔Projects` с rollup `Completion` — один-в-один паттерн для `Incident↔Task`, ~3-4 часа без миграции БД (главная фича для сессии b).

**Деплой:** `../deploy_session62_p0.py` (paramiko, бэкапы `.bak_session62`, рестарт). 4 файла. Перед деплоем сверить с продом (правило `feedback_deploy_over_prod.md`).

**Откат:**
```
ssh user@10.174.241.7
cd /home/user/portal
for f in app/children.py app/templates/incident_new.html \
         app/templates/incidents_dashboard.html app/templates/incidents_registry.html; do
  cp "$f.bak_session62" "$f"
done
pkill -9 -f 'python3 run.py'; nohup python3 run.py > /tmp/portal.log 2>&1 &
```

**Черновик s61 (на паузе)** восстановлен поверх s62 в working tree (не закомичен) — для целостности с предыдущей сессией. Содержит правки 8 файлов.

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
