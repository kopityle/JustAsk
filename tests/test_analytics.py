import json
import sqlite3
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.services import analytics_store


@pytest.fixture
def analytics_db(tmp_path, monkeypatch):
    db_path = tmp_path / "analytics.db"
    monkeypatch.setattr(analytics_store, "ANALYTICS_DB_PATH", db_path)
    return db_path


def _rows(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def _events(text):
    events = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        events.append("[DONE]" if payload == "[DONE]" else json.loads(payload))
    return events


async def _two_tokens(question, chunks, is_pure_greeting=False):
    yield "Секретный "
    yield "ответ ассистента"


def _chunk(document, page, text):
    return {"document": document, "page": page, "text": text}


def test_schema_stores_only_de_identified_fields(analytics_db):
    analytics_store.record_query("test_course", False)

    conn = sqlite3.connect(analytics_db)
    try:
        columns = {
            table: [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
            for table in ("query_stats", "source_hits")
        }
    finally:
        conn.close()

    assert columns["query_stats"] == ["id", "course_id", "is_found", "rating", "created_at"]
    assert columns["source_hits"] == ["id", "query_id", "course_id", "filename", "page", "rating"]
    all_columns = " ".join(sum(columns.values(), []))
    assert "question" not in all_columns
    assert "answer" not in all_columns
    assert "text" not in all_columns


def test_record_query_deduplicates_sources_and_nulls_non_pdf_pages(analytics_db):
    sources = [
        {"document": "lecture.pdf", "page": 3},
        {"document": "lecture.pdf", "page": 3},
        {"document": "notes.docx", "page": 7},
        {"document": "notes.txt", "page": 1},
        {"document": "slides.PDF", "page": "2"},
    ]

    event_id = analytics_store.record_query("course_a", True, sources)
    query_id = int(event_id)
    rows = _rows(analytics_db, "SELECT * FROM source_hits WHERE query_id = ?", (query_id,))

    assert len(rows) == 4
    assert {(row["filename"], row["page"]) for row in rows} == {
        ("lecture.pdf", 3),
        ("notes.docx", None),
        ("notes.txt", None),
        ("slides.PDF", 2),
    }
    query = _rows(analytics_db, "SELECT * FROM query_stats WHERE id = ?", (query_id,))[0]
    assert query["is_found"] == 1
    assert query["course_id"] == "course_a"
    assert query["created_at"]


def test_not_found_queries_do_not_create_source_hits(analytics_db):
    event_id = analytics_store.record_query(
        "course_a", False, [{"document": "lecture.pdf", "page": 1}]
    )

    assert _rows(analytics_db, "SELECT * FROM source_hits WHERE query_id = ?", (int(event_id),)) == []


def test_update_rating_copies_to_query_and_all_source_hits(analytics_db):
    event_id = analytics_store.record_query(
        "course_a",
        True,
        [{"document": "a.pdf", "page": 1}, {"document": "b.pdf", "page": 2}],
    )

    assert analytics_store.update_rating(event_id, "up") is True

    query = _rows(analytics_db, "SELECT rating FROM query_stats WHERE id = ?", (int(event_id),))[0]
    hits = _rows(analytics_db, "SELECT rating FROM source_hits WHERE query_id = ?", (int(event_id),))
    assert query["rating"] == "up"
    assert [hit["rating"] for hit in hits] == ["up", "up"]

    assert analytics_store.update_rating(event_id, "sideways") is False
    assert analytics_store.update_rating("not-an-id", "down") is False
    assert analytics_store.update_rating("999999", "down") is False
    query_again = _rows(analytics_db, "SELECT rating FROM query_stats WHERE id = ?", (int(event_id),))[0]
    assert query_again["rating"] == "up"


def test_delete_source_hits_is_scoped_to_course_and_filename(analytics_db):
    analytics_store.record_query("course_a", True, [{"document": "gone.pdf", "page": 2}])
    analytics_store.record_query("course_b", True, [{"document": "gone.pdf", "page": 2}])
    analytics_store.record_query("course_a", True, [{"document": "keep.pdf", "page": 2}])

    deleted = analytics_store.delete_source_hits("course_a", "gone.pdf")

    assert deleted == 1
    remaining = _rows(analytics_db, "SELECT course_id, filename FROM source_hits")
    assert {(row["course_id"], row["filename"]) for row in remaining} == {
        ("course_b", "gone.pdf"),
        ("course_a", "keep.pdf"),
    }


def test_summary_aggregates_totals_files_and_pages(analytics_db):
    q1 = analytics_store.record_query(
        "course_a", True, [{"document": "lecture.pdf", "page": 2}, {"document": "notes.docx", "page": 1}]
    )
    q2 = analytics_store.record_query(
        "course_a", True, [{"document": "lecture.pdf", "page": 2}, {"document": "lecture.pdf", "page": 3}]
    )
    q3 = analytics_store.record_query("course_a", False)
    analytics_store.record_query("course_b", True, [{"document": "other.pdf", "page": 1}])

    analytics_store.update_rating(q1, "up")
    analytics_store.update_rating(q2, "down")
    analytics_store.update_rating(q3, "down")

    summary = analytics_store.get_course_summary("course_a")

    assert summary["total_queries"] == 3
    assert summary["found_queries"] == 2
    assert summary["found_percentage"] == 66.7
    assert summary["upvotes"] == 1
    assert summary["downvotes"] == 2
    assert summary["usefulness_percentage"] == 33.3
    assert summary["files"] == [
        {"filename": "lecture.pdf", "citations": 3, "downvotes": 2, "upvotes": 1},
        {"filename": "notes.docx", "citations": 1, "downvotes": 0, "upvotes": 1},
    ]
    assert summary["pages"] == [
        {"filename": "lecture.pdf", "page": 2, "hits": 2, "downvotes": 1},
        {"filename": "lecture.pdf", "page": 3, "hits": 1, "downvotes": 1},
    ]


def test_summary_pages_are_capped_at_fifteen(analytics_db):
    for page in range(1, 18):
        analytics_store.record_query("course_a", True, [{"document": "many.pdf", "page": page}])

    pages = analytics_store.get_course_summary("course_a")["pages"]

    assert len(pages) == 15
    assert pages[0]["page"] == 1
    assert pages[-1]["page"] == 15


def test_chat_emits_event_id_and_feedback_updates_analytics(client, analytics_db, tmp_path):
    feedback_file = tmp_path / "feedback.jsonl"
    with patch("app.api.chat.settings.FEEDBACK_FILE", str(feedback_file)), \
         patch("app.api.chat.vector_store.search", return_value=[_chunk("lecture.pdf", 2, "цитата")]), \
         patch("app.api.chat.stream_rag_answer", side_effect=_two_tokens):
        response = client.post("/api/chat/stream", json={"question": "СЕКРЕТНЫЙ ВОПРОС СТУДЕНТА"})

    assert response.status_code == 200
    events = _events(response.text)
    assert events[-1] == "[DONE]"
    done = events[-2]
    assert done["type"] == "done"
    assert done["event_id"].isdigit()

    summary = analytics_store.get_course_summary("default_course")
    assert summary["total_queries"] == 1
    assert summary["files"][0]["filename"] == "lecture.pdf"

    res = client.post(
        "/api/feedback",
        json={
            "question": "СЕКРЕТНЫЙ ВОПРОС СТУДЕНТА",
            "answer": "СЕКРЕТНЫЙ ОТВЕТ АССИСТЕНТА",
            "is_positive": False,
            "event_id": done["event_id"],
        },
    )
    assert res.status_code == 200
    assert analytics_store.get_course_summary("default_course")["downvotes"] == 1
    hit = _rows(analytics_db, "SELECT rating FROM source_hits")[0]
    assert hit["rating"] == "down"

    db_dump = analytics_db.read_bytes().decode("utf-8", errors="ignore")
    assert "СЕКРЕТНЫЙ ВОПРОС СТУДЕНТА" not in db_dump
    assert "СЕКРЕТНЫЙ ОТВЕТ АССИСТЕНТА" not in db_dump
    assert "цитата" not in db_dump


def test_analytics_failures_never_break_student_requests(client, analytics_db, tmp_path):
    with patch("app.api.chat.vector_store.search", return_value=[_chunk("a.pdf", 1, "текст")]), \
         patch("app.api.chat.stream_rag_answer", side_effect=_two_tokens), \
         patch("app.api.chat.record_query", side_effect=RuntimeError("sqlite down")):
        response = client.post("/api/chat/stream", json={"question": "Обычный вопрос"})

    events = _events(response.text)
    assert response.status_code == 200
    assert events[-2]["type"] == "done"
    assert events[-1] == "[DONE]"

    with patch("app.api.chat.settings.FEEDBACK_FILE", str(tmp_path / "feedback.jsonl")), \
         patch("app.api.chat.update_rating", side_effect=RuntimeError("sqlite down")):
        res = client.post(
            "/api/feedback",
            json={"question": "Вопрос", "answer": "Ответ", "is_positive": True, "event_id": "1"},
        )
    assert res.status_code == 200
    assert res.json() == {"status": "recorded"}


def test_summary_is_teacher_only(client, student_headers, teacher_headers, analytics_db, monkeypatch):
    assert client.get("/api/analytics/summary").status_code == 403
    assert client.get("/api/analytics/summary", headers=student_headers).status_code == 403

    monkeypatch.setattr(settings, "ALLOW_GUEST_WRITES", True)
    assert client.get("/api/analytics/summary").status_code == 403

    response = client.get("/api/analytics/summary", headers=teacher_headers)
    assert response.status_code == 200
    assert response.json()["course_id"] == "test_course"
    assert response.json()["total_queries"] == 0


def test_delete_document_clears_its_analytics(client, tmp_path, teacher_headers, analytics_db, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    course_dir = tmp_path / "test_course"
    course_dir.mkdir()
    (course_dir / "gone.pdf").write_bytes(b"fake")
    analytics_store.record_query("test_course", True, [{"document": "gone.pdf", "page": 4}])

    monkeypatch.setattr(
        "app.api.documents.vector_store.delete_document",
        lambda filename, course_id=None: 1,
    )

    response = client.delete("/api/documents/gone.pdf", headers=teacher_headers)

    assert response.status_code == 200
    assert analytics_store.get_course_summary("test_course")["files"] == []


def test_delete_document_survives_analytics_failure(client, tmp_path, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    course_dir = tmp_path / "test_course"
    course_dir.mkdir()
    (course_dir / "file.pdf").write_bytes(b"fake")
    monkeypatch.setattr(
        "app.api.documents.vector_store.delete_document",
        lambda filename, course_id=None: 1,
    )
    monkeypatch.setattr(
        "app.api.documents.delete_source_hits",
        lambda course_id, filename: (_ for _ in ()).throw(RuntimeError("sqlite down")),
    )

    response = client.delete("/api/documents/file.pdf", headers=teacher_headers)

    assert response.status_code == 200


def test_reset_summary_is_teacher_only_and_scoped_to_course(client, student_headers, teacher_headers, analytics_db):
    analytics_store.record_query("test_course", True, [{"document": "course_a.pdf", "page": 1}])
    analytics_store.record_query("test_course", False)
    analytics_store.record_query("other_course", True, [{"document": "course_b.pdf", "page": 2}])

    assert client.delete("/api/analytics/summary", headers=student_headers).status_code == 403
    assert client.delete("/api/analytics/summary").status_code == 403
    assert len(_rows(analytics_db, "SELECT * FROM query_stats WHERE course_id = 'test_course'")) == 2

    response = client.delete("/api/analytics/summary", headers=teacher_headers)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert _rows(analytics_db, "SELECT * FROM query_stats WHERE course_id = 'test_course'") == []
    assert _rows(analytics_db, "SELECT * FROM source_hits WHERE course_id = 'test_course'") == []

    other_queries = _rows(analytics_db, "SELECT * FROM query_stats WHERE course_id = 'other_course'")
    other_hits = _rows(analytics_db, "SELECT * FROM source_hits WHERE course_id = 'other_course'")
    assert len(other_queries) == 1
    assert len(other_hits) == 1
    assert other_hits[0]["filename"] == "course_b.pdf"
