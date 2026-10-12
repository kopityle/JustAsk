from unittest.mock import patch
import os

def test_chat_stream_empty_question(client):
    response = client.post("/api/chat/stream", json={"question": "   "})
    assert response.status_code == 400

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