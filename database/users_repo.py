from database.db import get_db


def upsert_user(identity: dict) -> None:
    """Creates or refreshes a user's profile row. Expects the dict shape
    produced by utils/identity.py::extract_telegram_identity — does not
    touch questions_count (see increment_questions_count)."""
    db = get_db()
    db.execute(
        """
        INSERT INTO users (telegram_id, username, first_name, last_name, profile_link)
        VALUES (:id, :username, :first_name, :last_name, :profile_link)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            profile_link = excluded.profile_link,
            last_seen_at = CURRENT_TIMESTAMP
        """,
        identity,
    )
    db.commit()


def increment_questions_count(telegram_id: int) -> None:
    db = get_db()
    db.execute(
        "UPDATE users SET questions_count = questions_count + 1 WHERE telegram_id = ?",
        (telegram_id,),
    )
    db.commit()


def get_user(telegram_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    return dict(row) if row else None


def count_users() -> int:
    db = get_db()
    return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
