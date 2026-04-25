"""
Правка: Назначение роли CLASS_TEACHER классным руководителям
=============================================================

Проблема: все кл. руководители хранятся в user_role с кодом TEACHER.
has_role("CLASS_TEACHER") возвращает False → они не видят:
  - блок "Мой класс — 5А" на главной
  - секцию "Классное руководство" в хабе
  - список детей своего класса
  - карточки и соцпаспорт своих учеников

Решение: добавить CLASS_TEACHER в user_role для всех учителей,
у которых есть активный класс в текущем учебном году.
Роль TEACHER при этом остаётся — учитель получает обе роли.

Изменения в коде: НЕТ.
Изменения в файлах: НЕТ.
Рестарт сервера: НЕ НУЖЕН.
Вступает в силу: сразу, с первым запросом после применения.

Постоянно: ДА. Данные в БД, не слетят.
Новые кл. рук. в следующем году — добавлять через /admin/roles-admin вручную.
"""

import paramiko

HOST = "10.174.241.7"
PORT = 22
USER = "user"
PASSWORD = "RTYq"
DB_URL = "postgresql://school_user:StrongPassword123!@localhost/school_portal"

# Шаг 1: проверить — сколько учителей получат роль
SQL_CHECK = """
SELECT COUNT(DISTINCT sc.teacher_user_id) AS будет_обновлено
FROM school_class sc
CROSS JOIN (SELECT id FROM role WHERE code = 'CLASS_TEACHER') r
WHERE sc.teacher_user_id IS NOT NULL
  AND sc.academic_year_id = (SELECT id FROM academic_year WHERE is_current = true)
  AND sc.is_active = true
  AND NOT EXISTS (
    SELECT 1 FROM user_role ur2
    WHERE ur2.user_id = sc.teacher_user_id AND ur2.role_id = r.id
  );
"""

# Шаг 2: добавить CLASS_TEACHER в user_role
SQL_MIGRATE = """
INSERT INTO user_role (user_id, role_id)
SELECT DISTINCT sc.teacher_user_id, r.id
FROM school_class sc
CROSS JOIN (SELECT id FROM role WHERE code = 'CLASS_TEACHER') r
WHERE sc.teacher_user_id IS NOT NULL
  AND sc.academic_year_id = (SELECT id FROM academic_year WHERE is_current = true)
  AND sc.is_active = true
  AND NOT EXISTS (
    SELECT 1 FROM user_role ur2
    WHERE ur2.user_id = sc.teacher_user_id AND ur2.role_id = r.id
  );
"""

# Шаг 3: проверить результат
SQL_VERIFY = """
SELECT u.last_name || ' ' || u.first_name AS фио,
       sc.name AS класс
FROM school_class sc
JOIN "user" u ON u.id = sc.teacher_user_id
JOIN academic_year ay ON ay.id = sc.academic_year_id
WHERE ay.is_current = true
  AND sc.is_active = true
  AND sc.teacher_user_id IS NOT NULL
ORDER BY sc.name
LIMIT 20;
"""


def run_sql(ssh, sql, label):
    cmd = f"psql {DB_URL} << 'EOSQL'\n{sql.strip()}\nEOSQL"
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    print(f"\n[{label}]")
    if out:
        print(out)
    if err and "ERROR" in err.upper():
        print(f"  ОШИБКА: {err}")
        return False
    return True


def deploy():
    print(f"Подключаюсь к {HOST}:{PORT}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD)
    print("Подключён.\n")

    # Шаг 1: сколько будет обновлено
    ok = run_sql(ssh, SQL_CHECK, "Проверка: сколько учителей получат CLASS_TEACHER")
    if not ok:
        ssh.close()
        return

    # Шаг 2: применяем
    print("\n" + "=" * 50)
    print("Применяю миграцию...")
    print("=" * 50)
    ok = run_sql(ssh, SQL_MIGRATE, "INSERT user_role -> CLASS_TEACHER")
    if not ok:
        print("\nМиграция не выполнена. Проверь ошибки выше.")
        ssh.close()
        return

    # Шаг 3: верификация — первые 20 кл. рук.
    run_sql(ssh, SQL_VERIFY, "Первые 20 классных руководителей (проверка)")

    ssh.close()
    print("\n" + "=" * 50)
    print("Готово. Классные руководители теперь видят:")
    print("  - блок 'Мой класс' на главной")
    print("  - секцию 'Классное руководство' в хабе")
    print("  - только своих учеников в /children")
    print("  - карточки и соцпаспорт своих детей")
    print("Рестарт сервера не нужен — работает сразу.")
    print("=" * 50)


if __name__ == "__main__":
    deploy()
