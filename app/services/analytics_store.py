"""De-identified per-course usage analytics.

Only aggregate counters are stored here: no student question, generated answer
or quoted source text ever reaches this database. Every public helper is
failure-tolerant so analytics can never break a student-facing response.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

ANALYTICS_DB_PATH = PROJECT_ROOT / "data" / "analytics.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS query_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT NOT NULL,
    is_found INTEGER NOT NULL CHECK (is_found IN (0, 1)),
    rating TEXT CHECK (rating IN ('up', 'down')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_hits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL,
    course_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    page INTEGER,
    rating TEXT CHECK (rating IN ('up', 'down')),
    FOREIGN KEY (query_id) REFERENCES query_stats(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_query_stats_course ON query_stats(course_id);
CREATE INDEX IF NOT EXISTS idx_source_hits_course_file ON source_hits(course_id, filename);
CREATE INDEX IF NOT EXISTS idx_source_hits_query ON source_hits(query_id);
"""

_NON_PAGE_EXTENSIONS = {".txt", ".docx"}


@contextmanager
def _connection():
    """Open a short-lived connection and keep the schema current."""
    path = Path(ANALYTICS_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _normalize_filename(value: Any) -> str:
    return str(value or "").strip()[:255]


def _normalize_page(filename: str, value: Any) -> int | None:
    """TXT/DOCX chunks carry placeholder page numbers, so store NULL for them."""
    if os.path.splitext(filename)[1].lower() in _NON_PAGE_EXTENSIONS:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _percent(part: int, total: int) -> float:
    return round(part * 100 / total, 1) if total else 0.0


def record_query(
    course_id: str,
    is_found: bool,
    sources: Iterable[Mapping[str, Any]] | None = None,
) -> str:
    """Store one finished query plus its unique source pairs.

    Returns a public event id for the SSE `done` event. If storage fails, a
    random id is returned so the response stream still completes normally.
    """
    fallback_id = uuid.uuid4().hex
    try:
        with _connection() as conn:
            cursor = conn.execute(
                "INSERT INTO query_stats (course_id, is_found, created_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (str(course_id or "default_course"), 1 if is_found else 0),
            )
            query_id = int(cursor.lastrowid)

            if is_found and sources:
                seen: set[tuple[str, int | None]] = set()
                for source in sources:
                    if not isinstance(source, Mapping):
                        continue
                    filename = _normalize_filename(source.get("document"))
                    if not filename:
                        continue
                    page = _normalize_page(filename, source.get("page"))
                    key = (filename, page)
                    if key in seen:
                        continue
                    seen.add(key)
                    conn.execute(
                        "INSERT INTO source_hits (query_id, course_id, filename, page) "
                        "VALUES (?, ?, ?, ?)",
                        (query_id, str(course_id or "default_course"), filename, page),
                    )
        return str(query_id)
    except Exception:
        logger.exception("Не удалось записать аналитику запроса")
        return fallback_id


def update_rating(event_id: str | None, rating: str) -> bool:
    """Copy a feedback rating to the query and all of its source hits."""
    if rating not in {"up", "down"}:
        return False
    try:
        query_id = int(str(event_id).strip())
    except (TypeError, ValueError):
        return False

    try:
        with _connection() as conn:
            cursor = conn.execute(
                "UPDATE query_stats SET rating = ? WHERE id = ?", (rating, query_id)
            )
            if cursor.rowcount == 0:
                return False
            conn.execute(
                "UPDATE source_hits SET rating = ? WHERE query_id = ?",
                (rating, query_id),
            )
        return True
    except Exception:
        logger.exception("Не удалось обновить оценку в аналитике")
        return False


def delete_source_hits(course_id: str, filename: str) -> int:
    """Drop citation rows when a document is removed from the course."""
    try:
        with _connection() as conn:
            cursor = conn.execute(
                "DELETE FROM source_hits WHERE course_id = ? AND filename = ?",
                (str(course_id or "default_course"), str(filename or "")),
            )
            return cursor.rowcount
    except Exception:
        logger.exception("Не удалось удалить цитирования файла из аналитики")
        return 0


def get_course_summary(course_id: str) -> dict[str, Any]:
    """Aggregate de-identified counters for one course."""
    course = str(course_id or "default_course")
    empty: dict[str, Any] = {
        "course_id": course,
        "total_queries": 0,
        "found_queries": 0,
        "found_percentage": 0.0,
        "upvotes": 0,
        "downvotes": 0,
        "usefulness_percentage": 0.0,
        "files": [],
        "pages": [],
    }

    try:
        with _connection() as conn:
            totals = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN is_found = 1 THEN 1 ELSE 0 END), 0) AS found,
                       COALESCE(SUM(CASE WHEN rating = 'up' THEN 1 ELSE 0 END), 0) AS upvotes,
                       COALESCE(SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END), 0) AS downvotes
                FROM query_stats
                WHERE course_id = ?
                """,
                (course,),
            ).fetchone()

            files = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT filename,
                           COUNT(*) AS citations,
                           COALESCE(SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END), 0) AS downvotes,
                           COALESCE(SUM(CASE WHEN rating = 'up' THEN 1 ELSE 0 END), 0) AS upvotes
                    FROM source_hits
                    WHERE course_id = ?
                    GROUP BY filename
                    ORDER BY citations DESC, downvotes DESC, filename ASC
                    """,
                    (course,),
                )
            ]

            pages = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT filename, page,
                           COUNT(*) AS hits,
                           COALESCE(SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END), 0) AS downvotes
                    FROM source_hits
                    WHERE course_id = ? AND page IS NOT NULL
                    GROUP BY filename, page
                    ORDER BY hits DESC, downvotes DESC, filename ASC, page ASC
                    LIMIT 15
                    """,
                    (course,),
                )
            ]

        total = int(totals["total"])
        found = int(totals["found"])
        upvotes = int(totals["upvotes"])
        downvotes = int(totals["downvotes"])
        return {
            "course_id": course,
            "total_queries": total,
            "found_queries": found,
            "found_percentage": _percent(found, total),
            "upvotes": upvotes,
            "downvotes": downvotes,
            "usefulness_percentage": _percent(upvotes, upvotes + downvotes),
            "files": files,
            "pages": pages,
        }
    except Exception:
        logger.exception("Не удалось собрать аналитику курса")
        return empty
