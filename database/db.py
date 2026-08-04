import logging
import os
import sqlite3
import threading

from config.settings import DB_PATH
from database.seed_data import DEFAULT_PROJECT_CONTEXT

_local = threading.local()
_all_conns: list[sqlite3.Connection] = []
_all_conns_lock = threading.Lock()


def get_db() -> sqlite3.Connection:
    # Bot handlers run in multiple threads (see telebot threaded=True). A single
    # sqlite3.Connection shared across threads — even with check_same_thread=False —
    # can raise "bad parameter or other API misuse" under concurrent access, so each
    # thread gets its own connection instead; WAL + a busy timeout let them all read/write
    # the same file concurrently without "database is locked" errors.
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.conn = conn
        with _all_conns_lock:
            _all_conns.append(conn)
    return conn


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_id     INTEGER PRIMARY KEY,
            username        TEXT,
            first_name      TEXT,
            last_name       TEXT,
            profile_link    TEXT,
            first_seen_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            questions_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS chats (
            chat_id     INTEGER PRIMARY KEY,
            title       TEXT,
            active      BOOLEAN DEFAULT 0,
            enabled_at  TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id         INTEGER NOT NULL,
            user_id         INTEGER NOT NULL,
            message_id      INTEGER NOT NULL,
            text            TEXT    NOT NULL,
            is_reply_to_bot BOOLEAN DEFAULT 0,
            relevant        BOOLEAN DEFAULT 0,
            reply_text      TEXT    DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_messages_user
            ON messages(user_id, relevant, created_at);

        CREATE TABLE IF NOT EXISTS project_context (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            text        TEXT    DEFAULT '',
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by  INTEGER
        );

        CREATE TABLE IF NOT EXISTS trip_context (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            text        TEXT    DEFAULT '',
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by  INTEGER
        );

        -- Global kill switch (/pause, /resume) — independent of each chat's
        -- own active flag in `chats`. Paused overrides every chat at once,
        -- without touching their individual active flags, so /resume brings
        -- back exactly what was enabled before, with no need to re-/enable
        -- each chat one by one.
        CREATE TABLE IF NOT EXISTS bot_state (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            paused      BOOLEAN DEFAULT 0,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by  INTEGER
        );
    """
    )

    # Seed the evergreen project context with a sensible default so /context
    # shows something useful before any admin has ever run the command.
    # INSERT OR IGNORE is a no-op once row id=1 exists — including after an
    # admin has overwritten it via /context — so this never clobbers an edit.
    db.execute(
        "INSERT OR IGNORE INTO project_context (id, text) VALUES (1, ?)",
        (DEFAULT_PROJECT_CONTEXT,),
    )

    db.commit()
    logging.info("Database initialized: %s", DB_PATH)


def close_db() -> None:
    # Runs from the signal handler on the main thread, but connections opened
    # by telebot's worker threads (see get_db()'s comment) belong to those
    # threads — sqlite3 raises ProgrammingError if closed from any other
    # thread. Best-effort close; skip what we can't, the OS reclaims the file
    # descriptors on process exit either way.
    with _all_conns_lock:
        for conn in _all_conns:
            try:
                conn.close()
            except sqlite3.ProgrammingError:
                pass
        _all_conns.clear()
    _local.conn = None
