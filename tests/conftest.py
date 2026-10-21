import os
import pytest, jwt
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "test_jwt_secret_at_least_32_bytes_long_123")
os.environ.setdefault("LTI_CONSUMER_KEY", "test_moodle_consumer_key")
os.environ.setdefault("LTI_SHARED_SECRET", "test_lti_shared_secret")

from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

JWT_SECRET = settings.JWT_SECRET


@pytest.fixture(autouse=True)
def mock_ollama():
    """Подмена вызовов эмбеддера и пропуск индексации на старте приложения."""
    with patch("app.main.vector_store.count", return_value=1), patch(
        "app.services.vector_store.FastEmbedFunction.__call__",
        side_effect=lambda input: [[0.0] * 8 for _ in input],
    ):
        yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def student_token():
    payload = {"role": "student", "course_id": "test_course", "name": "Иван Студент"}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def teacher_token():
    payload = {"role": "teacher", "course_id": "test_course", "name": "Преподаватель"}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def student_headers(student_token):
    return {"Authorization": f"Bearer {student_token}"}


@pytest.fixture
def teacher_headers(teacher_token):
    return {"Authorization": f"Bearer {teacher_token}"}
