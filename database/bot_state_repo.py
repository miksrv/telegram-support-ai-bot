"""
Global kill switch — see the `bot_state` table comment in database/db.py.
Set via /pause and /resume (handlers/command_handler.py), checked once at
the top of handlers/message_handler.py's catch-all before anything else.
"""

from database.db import get_db


def is_paused() -> bool:
    db = get_db()
    row = db.execute("SELECT paused FROM bot_state WHERE id = 1").fetchone()
    return bool(row and row["paused"])


def set_paused(paused: bool, updated_by: int) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO bot_state (id, paused, updated_at, updated_by)
        VALUES (1, ?, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(id) DO UPDATE SET
            paused = excluded.paused,
            updated_at = excluded.updated_at,
            updated_by = excluded.updated_by
        """,
        (paused, updated_by),
    )
    db.commit()
