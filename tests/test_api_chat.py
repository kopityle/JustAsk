import asyncio
import json
import os
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import pytest
from fastapi import Request

from app.api.chat import dedupe_chunks
from app.api.documents import safe_course_id
from app.core.config import settings

def test_chat_stream_empty_question(client):
    response = client.post("/api/chat/stream", json={"question": "   "})
    assert response.status_code == 400


def test_chat_rejects_question_longer_than_4000(client):
    response = client.post("/api/chat/stream", json={"question": "x" * 4001})
    assert response.status_code == 422


def test_chat_normalizes_course_id_from_token(client):
    raw_course_id = "../Other Course/1"
    token = jwt.encode(
        {"role": "student", "course_id": raw_course_id, "name": "Студент"},
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    with patch("app.api.chat.vector_store.search", return_value=[]) as mock_search:
        response = client.post(
            "/api/chat/stream",
            json={"question": "Что такое база данных?"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    mock_search.assert_called_once_with(
        "Что такое база данных?",
        top_k=4,
        course_id=safe_course_id(raw_course_id),
    )

@patch("app.api.chat.vector_store.search")
def test_chat_fast_fail_offtopic(mock_search, client):
    # Если векторный поиск не нашел чанков с дистанцией <= 0.65
    mock_search.return_value = []
    
    response = client.post("/api/chat/stream", json={"question": "Как сварить борщ на Марсе?"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    
    # Должен сразу отдать отказ без вызова LLM
    text = response.text
    assert '"is_found": false' in text
    assert "В материалах курса ответ на этот вопрос не найден." in text

@patch("app.api.chat.stream_rag_answer")
def test_chat_pure_greeting(mock_stream, client):
    # Приветствие не должно идти в векторный поиск
    async def fake_stream(*args, **kwargs):
        yield "Привет! Чем могу помочь?"
    mock_stream.return_value = fake_stream()

    response = client.post("/api/chat/stream", json={"question": "Привет!"})
    assert response.status_code == 200
    text = response.text
    assert '"is_found": true' in text

def test_feedback_submit(client, tmp_path):
    # Проверяем запись отзыва
    test_file = tmp_path / "test_feedback.jsonl"
    with patch("app.api.chat.settings.FEEDBACK_FILE", str(test_file)):
        payload = {
            "question": "Что такое git?",
            "answer": "Это система контроля версий",
            "is_positive": True
        }
        res = client.post("/api/feedback", json=payload)
        assert res.status_code == 200
        assert res.json() == {"status": "recorded"}
        # Проверяем что файл создался во временной директории
        assert os.path.exists(test_file)


def _chunk(document, page, text):
    return {"document": document, "page": page, "text": text, "distance": 0.1}


def _events(text):
    events = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        events.append("[DONE]" if payload == "[DONE]" else json.loads(payload))
    return events


def _token_events(events):
    return [event["token"] for event in events if isinstance(event, dict) and event.get("type") == "token"]


async def _two_tokens(question, chunks, is_pure_greeting=False):
    yield "Короткий "
    yield "ответ"


def test_dedupe_chunks_removes_duplicates_and_respects_limit():
    chunks = [
        _chunk("a.pdf", 1, "одинаковый"),
        _chunk("a.pdf", 1, "одинаковый"),
        _chunk("b.pdf", 2, "второй"),
        _chunk("c.pdf", 3, "третий"),
        _chunk("d.pdf", 4, "четвёртый"),
    ]

    result = dedupe_chunks(chunks, limit=3)

    assert [chunk["document"] for chunk in result] == ["a.pdf", "b.pdf", "c.pdf"]


@patch("app.api.chat.stream_rag_answer")
@patch("app.api.chat.vector_store.search")
def test_chat_stream_found_chunks_emits_meta_tokens_and_done(mock_search, mock_stream, client):
    mock_search.return_value = [
        _chunk("db.pdf", 1, "Описание базы данных"),
        _chunk("db.pdf", 1, "Описание базы данных"),  # дубль той же страницы
        _chunk("db.pdf", 2, "Индексы"),
    ]
    mock_stream.side_effect = _two_tokens

    response = client.post("/api/chat/stream", json={"question": "Что такое база данных?"})

    assert response.status_code == 200
    assert response.headers["x-accel-buffering"] == "no"
    events = _events(response.text)
    meta = events[0]
    assert meta["type"] == "meta"
    assert meta["is_found"] is True
    assert meta["sources"] == [
        {"document": "db.pdf", "page": 1, "text": "Описание базы данных"},
        {"document": "db.pdf", "page": 2, "text": "Индексы"},
    ]
    assert _token_events(events) == ["Короткий ", "ответ"]
    assert events[-1] == "[DONE]"
    mock_search.assert_called_once_with("Что такое база данных?", top_k=4, course_id="default_course")


def test_chat_stream_expands_query_after_empty_first_search(client):
    found = [_chunk("1nf.pdf", 1, "первая нормальная форма")]
    with patch("app.api.chat.vector_store.search", side_effect=[[], found]) as mock_search, \
         patch("app.api.chat.expand_query", new=AsyncMock(return_value=["первая нормальная форма"])) as mock_expand, \
         patch("app.api.chat.stream_rag_answer", side_effect=_two_tokens):
        response = client.post("/api/chat/stream", json={"question": "Что такое 1НФ?"})

    assert response.status_code == 200
    mock_expand.assert_awaited_once_with("Что такое 1НФ?")
    assert mock_search.call_args_list[1].args[0] == "первая нормальная форма"
    events = _events(response.text)
    assert events[0]["sources"][0]["document"] == "1nf.pdf"
    assert _token_events(events) == ["Короткий ", "ответ"]
    assert events[-1] == "[DONE]"


def test_chat_stream_expand_timeout_falls_back_to_fast_reject(client):
    async def timeout(*args, **kwargs):
        raise asyncio.TimeoutError

    with patch("app.api.chat.vector_store.search", return_value=[]) as mock_search, \
         patch("app.api.chat.expand_query", new=AsyncMock(side_effect=timeout)), \
         patch("app.api.chat.stream_rag_answer") as mock_stream:
        response = client.post("/api/chat/stream", json={"question": "Что такое 1НФ?"})

    assert response.status_code == 200
    assert mock_search.call_count == 1
    mock_stream.assert_not_called()
    events = _events(response.text)
    assert events[0]["is_found"] is False
    assert _token_events(events) == ["В материалах курса ответ на этот вопрос не найден."]
    assert events[-1] == "[DONE]"


def test_chat_stream_propagates_ollama_error_as_token(client):
    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            raise httpx.ConnectError("network down")

        async def __aexit__(self, *args):
            return False

    with patch("app.api.chat.vector_store.search", return_value=[_chunk("db.pdf", 1, "текст")]), \
         patch("app.services.llm_client.httpx.AsyncClient", FailingAsyncClient):
        response = client.post("/api/chat/stream", json={"question": "Что такое база данных?"})

    events = _events(response.text)
    assert any("Ошибка при обращении к локальной модели Ollama" in token for token in _token_events(events))
    assert events[-1] == "[DONE]"


def test_stream_releases_semaphore_on_error_inside_stream(client, monkeypatch):
    semaphore = asyncio.BoundedSemaphore(1)
    monkeypatch.setattr("app.api.chat.inference_semaphore", semaphore)

    async def failing_stream(question, chunks, is_pure_greeting=False):
        yield "первый токен"
        raise RuntimeError("stream broke")

    with patch("app.api.chat.vector_store.search", return_value=[_chunk("db.pdf", 1, "текст")]), \
         patch("app.api.chat.stream_rag_answer", side_effect=failing_stream):
        with pytest.raises(RuntimeError, match="stream broke"):
            client.post("/api/chat/stream", json={"question": "Что такое база данных?"})

    assert not semaphore.locked()


def test_stream_releases_semaphore_when_client_disconnects(client, monkeypatch):
    semaphore = asyncio.BoundedSemaphore(1)
    monkeypatch.setattr("app.api.chat.inference_semaphore", semaphore)

    async def never_delivered(question, chunks, is_pure_greeting=False):
        yield "не должен попасть в ответ"

    with patch("app.api.chat.vector_store.search", return_value=[_chunk("db.pdf", 1, "текст")]), \
         patch("app.api.chat.stream_rag_answer", side_effect=never_delivered), \
         patch.object(Request, "is_disconnected", new=AsyncMock(return_value=True)):
        response = client.post("/api/chat/stream", json={"question": "Что такое база данных?"})

    events = _events(response.text)
    assert events[0]["type"] == "meta"
    assert _token_events(events) == []
    assert events[-1] == "[DONE]"
    assert not semaphore.locked()


def test_stream_returns_overload_warning_on_semaphore_timeout(client, monkeypatch):
    class BusySemaphore:
        def __init__(self):
            self.released = False

        async def acquire(self):
            raise asyncio.TimeoutError

        def release(self):
            self.released = True

    busy = BusySemaphore()
    monkeypatch.setattr("app.api.chat.inference_semaphore", busy)

    with patch("app.api.chat.vector_store.search", return_value=[_chunk("db.pdf", 1, "текст")]), \
         patch("app.api.chat.stream_rag_answer") as mock_stream:
        response = client.post("/api/chat/stream", json={"question": "Что такое база данных?"})

    events = _events(response.text)
    assert len(events) == 2
    assert "перегружен" in events[0]["token"]
    assert events[1] == "[DONE]"
    assert busy.released is False
    mock_stream.assert_not_called()
