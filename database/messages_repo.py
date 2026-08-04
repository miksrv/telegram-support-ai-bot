from database.db import get_db
from database.users_repo import increment_questions_count


def save_message(
    *,
    chat_id: int,
    user_id: int,
    message_id: int,
    text: str,
    is_reply_to_bot: bool,
    relevant: bool,
    reply_text: str,
) -> None:
    """Saves every observed message unconditionally — answered or not — so
    the DB keeps growing into a usable FAQ/history dataset (see CLAUDE.md)."""
    db = get_db()
    db.execute(
        """
        INSERT INTO messages (chat_id, user_id, message_id, text, is_reply_to_bot, relevant, reply_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (chat_id, user_id, message_id, text, is_reply_to_bot, relevant, reply_text),
    )
    db.commit()

    if relevant:
        increment_questions_count(user_id)


def get_user_history(user_id: int, limit: int) -> list[dict]:
    """
    Returns the user's last `limit` answered questions (relevant=1) across
    all chats, oldest first, so it reads naturally as a conversation when
    injected into the LLM prompt.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT text, reply_text, created_at
        FROM messages
        WHERE user_id = ? AND relevant = 1
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in reversed(rows)]


def count_messages(relevant_only: bool = False) -> int:
    db = get_db()
    if relevant_only:
        return db.execute("SELECT COUNT(*) FROM messages WHERE relevant = 1").fetchone()[0]
    return db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]


def count_answered_by_chat() -> list[dict]:
    db = get_db()
    rows = db.execute(
        """
        SELECT chat_id, COUNT(*) AS answered
        FROM messages
        WHERE relevant = 1
        GROUP BY chat_id
        ORDER BY answered DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]
