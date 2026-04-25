import os
import sqlite3
from urllib.parse import urlparse
from datetime import datetime

import psycopg2
from psycopg2 import sql


SQLITE_PATH = os.path.abspath(os.path.join("data", "app.db"))
POSTGRES_URL = "postgresql://school_user:StrongPassword123@localhost:5432/school_tracker"

TABLES = [
    "academic_year",
    "buildings",
    "user",
    "school_class",
    "subject",
    "child",
    "child_enrollment",
    "debt",
    "document",
    "child_comments",
    "child_events",
    "incident",
    "incident_child",
]


def get_sqlite_conn():
    return sqlite3.connect(SQLITE_PATH)


def get_postgres_conn():
    parsed = urlparse(POSTGRES_URL)
    return psycopg2.connect(
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port,
    )


def sqlite_table_exists(conn, table_name):
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    row = cur.fetchone()
    cur.close()
    return row is not None


def fetch_rows(sqlite_conn, table_name):
    cur = sqlite_conn.cursor()
    cur.execute(f'SELECT * FROM "{table_name}"')
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close()
    return cols, rows


def truncate_postgres_tables(pg_conn):
    cur = pg_conn.cursor()
    cur.execute("""
        TRUNCATE TABLE
            incident_child,
            incident,
            child_events,
            child_comments,
            document,
            debt,
            child_enrollment,
            child,
            school_class,
            subject,
            buildings,
            "user",
            academic_year
        RESTART IDENTITY CASCADE
    """)
    pg_conn.commit()
    cur.close()


def get_pg_bool_columns(pg_conn, table_name):
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND data_type = 'boolean'
    """, (table_name,))
    result = {row[0] for row in cur.fetchall()}
    cur.close()
    return result

def normalize_row(table_name, cols, row, bool_cols):
    cols = list(cols)
    values = list(row)

    if table_name == "debt":
        # legacy-поля, которых нет в новой модели
        for legacy_col in [
            "comment",
            "responsible_user_id",
            "responsible_fio",
            "responsible_phone",
        ]:
            if legacy_col in cols:
                idx = cols.index(legacy_col)
                cols.pop(idx)
                values.pop(idx)

        # closed_date -> closed_at
        if "closed_date" in cols and "closed_at" not in cols:
            idx = cols.index("closed_date")
            cols[idx] = "closed_at"

        # если есть и closed_date, и closed_at — удаляем closed_date
        if "closed_date" in cols and "closed_at" in cols:
            idx = cols.index("closed_date")
            cols.pop(idx)
            values.pop(idx)

        # если created_at пустой — ставим detected_date или текущее время
        if "created_at" in cols:
            idx_created = cols.index("created_at")
            if values[idx_created] in (None, "",):
                if "detected_date" in cols:
                    idx_detected = cols.index("detected_date")
                    detected_value = values[idx_detected]
                    if detected_value not in (None, "",):
                        values[idx_created] = f"{detected_value} 00:00:00"
                    else:
                        values[idx_created] = datetime.utcnow()
                else:
                    values[idx_created] = datetime.utcnow()

    if table_name == "child_events":
        # старое поле text в новой модели отсутствует
        if "text" in cols:
            idx = cols.index("text")
            cols.pop(idx)
            values.pop(idx)

    normalized = []
    for col, value in zip(cols, values):
        if col in bool_cols and value is not None:
            normalized.append(bool(value))
        else:
            normalized.append(value)

    return cols, normalized

def copy_table(sqlite_conn, pg_conn, table_name):
    if not sqlite_table_exists(sqlite_conn, table_name):
        print(f"[SKIP] Таблица {table_name} отсутствует в SQLite")
        return

    cols, rows = fetch_rows(sqlite_conn, table_name)
    if not rows:
        print(f"[OK] {table_name}: пусто")
        return

    bool_cols = get_pg_bool_columns(pg_conn, table_name)

    cur = pg_conn.cursor()
    inserted = 0

    for row in rows:
        final_cols, normalized_row = normalize_row(table_name, cols, row, bool_cols)

        placeholders = sql.SQL(", ").join(sql.Placeholder() * len(final_cols))
        columns_sql = sql.SQL(", ").join(sql.Identifier(c) for c in final_cols)

        insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table_name),
            columns_sql,
            placeholders
        )

        cur.execute(insert_sql, normalized_row)
        inserted += 1

    pg_conn.commit()
    cur.close()

    print(f"[OK] {table_name}: перенесено {inserted} строк")


def main():
    print("SQLite:", SQLITE_PATH)
    print("PostgreSQL:", POSTGRES_URL)

    sqlite_conn = get_sqlite_conn()
    pg_conn = get_postgres_conn()

    try:
        print("Очищаю PostgreSQL...")
        truncate_postgres_tables(pg_conn)

        for table in TABLES:
            copy_table(sqlite_conn, pg_conn, table)

        print("Готово. Данные перенесены.")
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()