"""
Persistent project context + current trip context — two independently
updatable single-row tables (id = 1) rather than one blob, so an organizer
updating the trip details for a new event doesn't have to retype the parts
that never change. See CLAUDE.md's "/event and /context" section.
"""

from database.db import get_db

# Table names are hardcoded literals below, never user input.
_PROJECT_TABLE = "project_context"
_TRIP_TABLE = "trip_context"


def _get_context(table: str) -> str:
    db = get_db()
    row = db.execute(f"SELECT text FROM {table} WHERE id = 1").fetchone()
    return row["text"] if row else ""


def _set_context(table: str, text: str, updated_by: int) -> None:
    db = get_db()
    db.execute(
        f"""
        INSERT INTO {table} (id, text, updated_at, updated_by)
        VALUES (1, ?, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(id) DO UPDATE SET
            text = excluded.text,
            updated_at = excluded.updated_at,
            updated_by = excluded.updated_by
        """,
        (text, updated_by),
    )
    db.commit()


def get_project_context() -> str:
    return _get_context(_PROJECT_TABLE)


def set_project_context(text: str, updated_by: int) -> None:
    _set_context(_PROJECT_TABLE, text, updated_by)


def get_trip_context() -> str:
    return _get_context(_TRIP_TABLE)


def set_trip_context(text: str, updated_by: int) -> None:
    _set_context(_TRIP_TABLE, text, updated_by)
