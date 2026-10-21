import io
from app.core.config import settings

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
    assert not (tmp_path / "large.txt").exists()

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
    assert (tmp_path / "notes.PDF").exists()

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
