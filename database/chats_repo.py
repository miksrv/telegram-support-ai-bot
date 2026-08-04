from database.db import get_db


def set_active(chat_id: int, title: str, active: bool) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO chats (chat_id, title, active, enabled_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(chat_id) DO UPDATE SET
            title = excluded.title,
            active = excluded.active,
            enabled_at = CASE WHEN excluded.active THEN CURRENT_TIMESTAMP ELSE chats.enabled_at END
        """,
        (chat_id, title, active),
    )
    db.commit()


def is_active(chat_id: int) -> bool:
    db = get_db()
    row = db.execute("SELECT active FROM chats WHERE chat_id = ?", (chat_id,)).fetchone()
    return bool(row and row["active"])


def list_chats() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM chats ORDER BY title").fetchall()
    return [dict(row) for row in rows]
