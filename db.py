"""MySQL-backed storage for Reportly, swapped in for the old data/*.json files.

Keeps the exact same load_x()/save_x(data) interface the app already calls
(load returns a list of dicts, save takes the full list and persists it) so
app.py's route logic — which loads a list, mutates it in place, then saves
the whole thing back — didn't need to change at all. save_x() replaces the
table contents wholesale inside one transaction, which is fine at this
project's scale (a handful of roster members, ~20 projects, a few thousand
report rows at most).
"""

import os
import queue as _queue
import uuid
from datetime import datetime
from urllib.parse import quote

import pymysql
import pymysql.cursors

_MYSQL_POOL_MAX = 5


def _parse_mysql_url(url):
    """Parse mysql[+pymysql]://user:pass@host:port/dbname into pymysql.connect() kwargs."""
    url = url.strip()
    if url.startswith("mysql+pymysql://"):
        url = url[len("mysql+pymysql://"):]
    elif url.startswith("mysql://"):
        url = url[len("mysql://"):]
    user_pass, rest = url.split("@", 1)
    user, password = user_pass.split(":", 1)
    host_port, database = rest.split("/", 1)
    if ":" in host_port:
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        host, port = host_port, 3306
    return dict(host=host, port=port, user=user, password=password, database=database)


class _MySQLPool:
    def __init__(self, maxsize):
        self._pool = _queue.Queue(maxsize=maxsize)

    def _connect(self):
        kwargs = _parse_mysql_url(os.environ.get("DATABASE_URL", ""))
        return pymysql.connect(
            **kwargs, cursorclass=pymysql.cursors.DictCursor,
            charset="utf8mb4", autocommit=False,
        )

    def getconn(self):
        try:
            conn = self._pool.get_nowait()
        except _queue.Empty:
            return self._connect()
        try:
            conn.ping(reconnect=True)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            return self._connect()
        return conn

    def putconn(self, conn, close=False):
        if close:
            try:
                conn.close()
            except Exception:
                pass
            return
        try:
            self._pool.put_nowait(conn)
        except _queue.Full:
            conn.close()


_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = _MySQLPool(_MYSQL_POOL_MAX)
    return _pool


from contextlib import contextmanager


@contextmanager
def _db():
    conn = _get_pool().getconn()
    broken = False
    try:
        cur = conn.cursor()
        yield conn, cur
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            broken = True
        raise
    finally:
        _get_pool().putconn(conn, close=broken)


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS roster (
            id            VARCHAR(64) PRIMARY KEY,
            name          TEXT NOT NULL,
            role          VARCHAR(32) NOT NULL DEFAULT 'member',
            username      VARCHAR(255) NOT NULL UNIQUE,
            password_hash TEXT,
            email         VARCHAR(255) UNIQUE
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS reports (
            id            VARCHAR(64) PRIMARY KEY,
            name          TEXT NOT NULL,
            date          VARCHAR(32) NOT NULL,
            raw_work      TEXT,
            raw_pending   TEXT,
            `generated`   TEXT,
            status        VARCHAR(32) NOT NULL DEFAULT 'draft',
            submitted_at  VARCHAR(32),
            logged_by     VARCHAR(255),
            logged_at     VARCHAR(32),
            edited_by     VARCHAR(255),
            edited_at     VARCHAR(32),
            INDEX idx_reports_date (date),
            INDEX idx_reports_name (name(191))
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS projects (
            id                VARCHAR(64) PRIMARY KEY,
            name              TEXT NOT NULL,
            description       TEXT,
            owner             TEXT,
            progress_summary  TEXT,
            status            VARCHAR(32) NOT NULL DEFAULT 'Not Started',
            percent_complete  INT NOT NULL DEFAULT 0,
            start_date        VARCHAR(64),
            deadline          VARCHAR(64),
            risks             TEXT,
            next_action       TEXT,
            kpi               TEXT,
            created_at        VARCHAR(32),
            updated_at        VARCHAR(32)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS changes (
            id           VARCHAR(64) PRIMARY KEY,
            project_id   VARCHAR(64),
            change_type  VARCHAR(64),
            summary      TEXT,
            description  TEXT,
            status       VARCHAR(32) NOT NULL DEFAULT 'Live',
            added_by     VARCHAR(255),
            added_at     VARCHAR(32),
            edited_by     VARCHAR(255),
            edited_at     VARCHAR(32),
            INDEX idx_changes_project (project_id)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci""",
]


def _run_migrations(cur):
    """Incremental schema changes for databases created before this column
    existed. Safe on every boot — swallows the "column already exists" error
    on every run after the first."""
    try:
        cur.execute("ALTER TABLE roster ADD COLUMN email VARCHAR(255) UNIQUE")
    except Exception:
        pass


def init_db():
    """Create tables if they don't exist. Idempotent, safe on every boot."""
    with _db() as (conn, cur):
        for stmt in _SCHEMA:
            cur.execute(stmt)
        _run_migrations(cur)


def _load_table(table, order_by=None):
    """Returns a plain list, never pymysql's raw fetchall() tuple — routes
    throughout app.py do `rows = load_x(); rows.append(...)`, which breaks on
    a tuple. Non-empty results happened to come back as lists already in
    practice, so this only ever bit an actually-empty table (e.g. adding the
    very first project/report/change/roster member on a fresh database)."""
    with _db() as (conn, cur):
        sql = f"SELECT * FROM {table}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        cur.execute(sql)
        return list(cur.fetchall())


_RESERVED = {"generated"}


def _qcol(name):
    return f"`{name}`" if name in _RESERVED else name


def _save_table(table, columns, rows):
    """Replace the full contents of `table` with `rows` (list of dicts)."""
    with _db() as (conn, cur):
        cur.execute(f"DELETE FROM {table}")
        if rows:
            placeholders = ", ".join(["%s"] * len(columns))
            col_list = ", ".join(_qcol(c) for c in columns)
            sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
            values = [tuple(row.get(col) for col in columns) for row in rows]
            cur.executemany(sql, values)


ROSTER_COLUMNS   = ["id", "name", "role", "username", "password_hash", "email"]
REPORTS_COLUMNS  = ["id", "name", "date", "raw_work", "raw_pending", "generated",
                     "status", "submitted_at", "logged_by", "logged_at",
                     "edited_by", "edited_at"]
PROJECTS_COLUMNS = ["id", "name", "description", "owner", "progress_summary",
                     "status", "percent_complete", "start_date", "deadline",
                     "risks", "next_action", "kpi", "created_at", "updated_at"]
CHANGES_COLUMNS  = ["id", "project_id", "change_type", "summary", "description",
                     "status", "added_by", "added_at", "edited_by", "edited_at"]


def load_roster():
    return _load_table("roster")


def save_roster(data):
    _save_table("roster", ROSTER_COLUMNS, data)


def load_reports():
    return _load_table("reports")


def save_reports(data):
    _save_table("reports", REPORTS_COLUMNS, data)


def load_projects():
    return _load_table("projects")


def save_projects(data):
    _save_table("projects", PROJECTS_COLUMNS, data)


def load_changes():
    return _load_table("changes")


def save_changes(data):
    _save_table("changes", CHANGES_COLUMNS, data)


def upsert_projects(rows):
    """Insert new projects / update existing ones by id, leaving any project not
    present in `rows` untouched. Used by the spreadsheet-upload route so
    re-uploading a sheet doesn't wipe out projects added directly in the UI.
    Preserves each existing project's original created_at — only its other
    columns (including updated_at) move to the sheet's values."""
    if not rows:
        return
    with _db() as (conn, cur):
        col_list = ", ".join(PROJECTS_COLUMNS)
        placeholders = ", ".join(["%s"] * len(PROJECTS_COLUMNS))
        update_cols = [c for c in PROJECTS_COLUMNS if c not in ("id", "created_at")]
        update_clause = ", ".join(f"{c}=VALUES({c})" for c in update_cols)
        sql = (f"INSERT INTO projects ({col_list}) VALUES ({placeholders}) "
               f"ON DUPLICATE KEY UPDATE {update_clause}")
        values = [tuple(row.get(col) for col in PROJECTS_COLUMNS) for row in rows]
        cur.executemany(sql, values)


def upsert_reports(rows):
    """Match existing reports by (name, date) — reports have no natural ID in
    the spreadsheet, unlike projects — and update only raw_work/raw_pending
    from the sheet, leaving id/status/`generated`/submitted_at/etc. alone so a
    re-upload can't downgrade an already-submitted, possibly AI-polished
    report back to raw sheet text. A (name, date) pair with no existing match
    is inserted as a new submitted report."""
    if not rows:
        return
    with _db() as (conn, cur):
        for row in rows:
            cur.execute(
                "SELECT id FROM reports WHERE name=%s AND date=%s",
                (row["name"], row["date"]),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE reports SET raw_work=%s, raw_pending=%s WHERE id=%s",
                    (row["raw_work"], row.get("raw_pending", ""), existing["id"]),
                )
            else:
                cur.execute(
                    "INSERT INTO reports (id, name, date, raw_work, raw_pending, "
                    "`generated`, status, submitted_at, logged_by, logged_at) "
                    "VALUES (%s, %s, %s, %s, %s, '', 'submitted', %s, %s, %s)",
                    (
                        str(uuid.uuid4())[:8], row["name"], row["date"],
                        row["raw_work"], row.get("raw_pending", ""),
                        f"{row['date']}T17:00:00",
                        "Spreadsheet Import", datetime.now().isoformat(),
                    ),
                )
