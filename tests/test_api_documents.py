import io

import jwt
import pytest

from app.core.config import settings


def teacher_headers_for_course(course_id):
    token = jwt.encode(
        {"role": "teacher", "course_id": course_id, "name": "Преподаватель"},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}

def test_guest_cannot_upload_by_default(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_GUEST_WRITES", False)
    file_data = io.BytesIO(b"fake pdf content")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("guest.pdf", file_data, "application/pdf")}
    )
    assert response.status_code == 403

def test_guest_can_upload_when_dev_flag_enabled(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_GUEST_WRITES", True)
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.api.documents.load_and_chunk_file",
        lambda path: [{"document": "guest.pdf", "page": 1, "text": "hello"}],
    )
    monkeypatch.setattr("app.api.documents.vector_store.add_chunks", lambda chunks, course_id=None: None)
    monkeypatch.setattr("app.api.documents.vector_store.delete_document", lambda filename, course_id=None: 0)

    file_data = io.BytesIO(b"fake pdf content")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("guest.pdf", file_data, "application/pdf")}
    )
    assert response.status_code == 200
    assert response.json()["indexed_chunks"] == 1
    assert (tmp_path / "default_course" / "guest.pdf").exists()

def test_student_cannot_upload(client, student_headers):
    file_data = io.BytesIO(b"fake pdf content")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test.pdf", file_data, "application/pdf")},
        headers=student_headers
    )
    assert response.status_code == 403
    assert "Загрузка доступна только преподавателю" in response.json()["detail"]

def test_student_cannot_delete(client, student_headers):
    response = client.delete("/api/documents/test.pdf", headers=student_headers)
    assert response.status_code == 403
    assert "Удаление доступно только преподавателю" in response.json()["detail"]

def test_upload_invalid_format(client, teacher_headers):
    file_data = io.BytesIO(b"malicious content")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("danger.exe", file_data, "application/octet-stream")},
        headers=teacher_headers
    )
    assert response.status_code == 400
    assert "Формат не поддерживается" in response.json()["detail"]

def test_upload_rejects_path_traversal(client, teacher_headers):
    file_data = io.BytesIO(b"fake pdf content")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("../evil.pdf", file_data, "application/pdf")},
        headers=teacher_headers
    )
    assert response.status_code == 400
    assert "Некорректное имя файла" in response.json()["detail"]

def test_upload_rejects_oversized_file(client, tmp_path, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 4)
    monkeypatch.setattr("app.api.documents.vector_store.delete_document", lambda filename, course_id=None: 0)

    file_data = io.BytesIO(b"12345")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("large.txt", file_data, "text/plain")},
        headers=teacher_headers
    )
    assert response.status_code == 413
    assert not (tmp_path / "test_course" / "large.txt").exists()

def test_upload_accepts_uppercase_extension(client, tmp_path, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.api.documents.load_and_chunk_file",
        lambda path: [{"document": "notes.PDF", "page": 1, "text": "hello"}],
    )
    monkeypatch.setattr("app.api.documents.vector_store.add_chunks", lambda chunks, course_id=None: None)

    file_data = io.BytesIO(b"fake pdf content")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("notes.PDF", file_data, "application/pdf")},
        headers=teacher_headers
    )
    assert response.status_code == 200
    assert (tmp_path / "test_course" / "notes.PDF").exists()


def test_upload_accepts_docx(client, tmp_path, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.api.documents.load_and_chunk_file",
        lambda path: [{"document": "notes.docx", "page": 1, "text": "hello"}],
    )
    monkeypatch.setattr("app.api.documents.vector_store.add_chunks", lambda chunks, course_id=None: None)
    monkeypatch.setattr("app.api.documents.vector_store.delete_document", lambda filename, course_id=None: 0)

    file_data = io.BytesIO(b"fake docx content")
    response = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "notes.docx",
                file_data,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=teacher_headers,
    )
    assert response.status_code == 200
    assert (tmp_path / "test_course" / "notes.docx").exists()


def test_same_filename_in_two_courses_does_not_conflict(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.api.documents.load_and_chunk_file",
        lambda path: [{"document": "lecture.pdf", "page": 1, "text": "hello"}],
    )
    monkeypatch.setattr("app.api.documents.vector_store.add_chunks", lambda chunks, course_id=None: None)
    monkeypatch.setattr("app.api.documents.vector_store.delete_document", lambda filename, course_id=None: 0)

    for course_id in ("course_a", "course_b"):
        file_data = io.BytesIO(b"fake pdf content")
        response = client.post(
            "/api/documents/upload",
            files={"file": ("lecture.pdf", file_data, "application/pdf")},
            headers=teacher_headers_for_course(course_id),
        )
        assert response.status_code == 200

    assert (tmp_path / "course_a" / "lecture.pdf").exists()
    assert (tmp_path / "course_b" / "lecture.pdf").exists()


def test_documents_info_reports_permissions(client, student_headers, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_GUEST_WRITES", False)

    guest = client.get("/api/documents")
    assert guest.status_code == 200
    assert guest.json()["can_manage"] is False
    assert guest.json()["dev_write_access"] is False

    student = client.get("/api/documents", headers=student_headers)
    assert student.status_code == 200
    assert student.json()["can_manage"] is False

    teacher = client.get("/api/documents", headers=teacher_headers)
    assert teacher.status_code == 200
    assert teacher.json()["can_manage"] is True

    monkeypatch.setattr(settings, "ALLOW_GUEST_WRITES", True)
    guest_dev = client.get("/api/documents")
    assert guest_dev.status_code == 200
    assert guest_dev.json()["can_manage"] is True
    assert guest_dev.json()["dev_write_access"] is True


def _mock_upload_pipeline(monkeypatch, chunks=None, add_error=None):
    chunks = [{"document": "lecture.pdf", "page": 1, "text": "hello"}] if chunks is None else chunks
    deleted = []
    added = []

    monkeypatch.setattr(
        "app.api.documents.load_and_chunk_file",
        lambda path: list(chunks),
    )
    monkeypatch.setattr(
        "app.api.documents.vector_store.delete_document",
        lambda filename, course_id=None: deleted.append((filename, course_id)) or 0,
    )

    def _add_chunks(items, course_id=None):
        added.append((course_id, items))
        if add_error is not None:
            raise add_error

    monkeypatch.setattr("app.api.documents.vector_store.add_chunks", _add_chunks)
    return deleted, added


def _upload_bytes(client, filename, headers):
    return client.post(
        "/api/documents/upload",
        files={"file": (filename, io.BytesIO(b"fake pdf content"), "application/pdf")},
        headers=headers,
    )


def test_upload_existing_file_in_same_course_returns_conflict(client, tmp_path, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    deleted, added = _mock_upload_pipeline(monkeypatch)

    assert _upload_bytes(client, "lecture.pdf", teacher_headers).status_code == 200
    conflict = _upload_bytes(client, "lecture.pdf", teacher_headers)

    assert conflict.status_code == 409
    assert "уже загружен" in conflict.json()["detail"]
    assert len(added) == 1
    assert len(deleted) == 1
    assert (tmp_path / "test_course" / "lecture.pdf").exists()


def test_upload_empty_file_returns_400_and_removes_temp_file(client, tmp_path, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    deleted, added = _mock_upload_pipeline(monkeypatch, chunks=[])

    response = _upload_bytes(client, "empty.pdf", teacher_headers)

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "не найден текст" in detail
    assert "OCR" in detail
    assert not (tmp_path / "test_course" / "empty.pdf").exists()
    assert added == []
    assert deleted == [("empty.pdf", "test_course")]


def test_upload_indexing_error_rolls_back_file(client, tmp_path, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    deleted, added = _mock_upload_pipeline(monkeypatch, add_error=RuntimeError("index failed"))

    with pytest.raises(RuntimeError, match="index failed"):
        _upload_bytes(client, "broken.pdf", teacher_headers)

    assert not (tmp_path / "test_course" / "broken.pdf").exists()
    assert len(added) == 1
    assert deleted and set(deleted) == {("broken.pdf", "test_course")}


def test_delete_document_full_cycle(client, tmp_path, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    course_dir = tmp_path / "test_course"
    course_dir.mkdir()
    file_path = course_dir / "delete_me.pdf"
    file_path.write_bytes(b"fake pdf content")

    deleted = []
    monkeypatch.setattr(
        "app.api.documents.vector_store.delete_document",
        lambda filename, course_id=None: deleted.append((filename, course_id)) or 1,
    )

    response = client.delete("/api/documents/delete_me.pdf", headers=teacher_headers)

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "filename": "delete_me.pdf", "removed_chunks": 1}
    assert deleted == [("delete_me.pdf", "test_course")]
    assert not file_path.exists()


def test_delete_missing_document_returns_404(client, tmp_path, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.api.documents.vector_store.delete_document",
        lambda filename, course_id=None: 0,
    )

    response = client.delete("/api/documents/absent.pdf", headers=teacher_headers)

    assert response.status_code == 404
    assert "Файл не найден" in response.json()["detail"]


def test_delete_document_cannot_touch_other_course(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCS_DIR", str(tmp_path))
    other_file = tmp_path / "other_course" / "secret.pdf"
    other_file.parent.mkdir()
    other_file.write_bytes(b"secret")

    deleted = []
    monkeypatch.setattr(
        "app.api.documents.vector_store.delete_document",
        lambda filename, course_id=None: deleted.append((filename, course_id))
        or (1 if course_id == "other_course" else 0),
    )

    response = client.delete(
        "/api/documents/secret.pdf",
        headers=teacher_headers_for_course("test_course"),
    )

    assert response.status_code == 404
    assert deleted == [("secret.pdf", "test_course")]
    assert other_file.exists()


@pytest.mark.parametrize("filename", ["con.pdf", "nul.txt", "aux.docx"])
def test_upload_rejects_windows_reserved_names(client, teacher_headers, filename):
    response = _upload_bytes(client, filename, teacher_headers)

    assert response.status_code == 400
    assert "Некорректное имя файла" in response.json()["detail"]

