from pathlib import Path
from unittest.mock import patch

import httpx

from app.core.config import settings
from app.main import STATIC_DIR


def test_static_dir_is_absolute():
    """Приложение должно запускаться из любого каталога, а не только из корня проекта."""
    assert Path(STATIC_DIR).is_absolute()
    assert (STATIC_DIR / "index.html").is_file()


class FakeOllamaClient:
    """Заглушка httpx.AsyncClient, чтобы не дёргать реальную Ollama в тестах."""

    instances = []

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")
        self.url = None
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        self.url = url
        return httpx.Response(200, json={"models": []})


def test_health_ok(client):
    FakeOllamaClient.instances.clear()

    with patch("app.main.httpx.AsyncClient", FakeOllamaClient):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "chunks": 1, "ollama": "ok"}
    client_stub = FakeOllamaClient.instances[0]
    assert client_stub.timeout == 2.0
    assert client_stub.url == f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"


def test_health_degraded_when_chroma_and_ollama_fail(client):
    class BrokenOllamaClient(FakeOllamaClient):
        async def __aenter__(self):
            raise httpx.ConnectError("network down")

    with patch("app.main.vector_store.count", side_effect=RuntimeError("chroma down")), \
         patch("app.main.httpx.AsyncClient", BrokenOllamaClient):
        response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["chunks"] is None
    assert body["ollama"] == "unavailable"
    assert len(body["errors"]) == 2
    assert any("ChromaDB" in error for error in body["errors"])
    assert any("Ollama" in error for error in body["errors"])


def test_health_degraded_when_ollama_returns_error(client):
    class ErrorOllamaClient(FakeOllamaClient):
        async def get(self, url):
            return httpx.Response(503)

    with patch("app.main.httpx.AsyncClient", ErrorOllamaClient):
        response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["chunks"] == 1
    assert body["ollama"] == "unavailable"
