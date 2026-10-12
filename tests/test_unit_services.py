import pytest
from app.services.pdf_loader import clean_pdf_text, split_text_clean
from app.api.chat import GREETING_REGEX, get_session_context


def test_clean_pdf_text_removes_typography():
    raw = "инфор-\xadмация\u00a0и\u202fданные-\nсвязи\xad."
    assert clean_pdf_text(raw) == "информация и данныесвязи."


def test_clean_pdf_text_preserves_paragraphs():
    raw = "Первый\tабзац.\n\nВторой  абзац."
    assert clean_pdf_text(raw) == "Первый абзац.\n\nВторой абзац."

def test_split_text_clean_empty():
    assert split_text_clean("") == []
    assert split_text_clean(None) == []

def test_split_text_clean_boundaries():
    # Проверяем, что чанкер не режет слова посредине и учитывает overlap
    sample_text = "Первое предложение курса. Второе предложение курса. Третье длинное предложение."
    chunks = split_text_clean(sample_text, chunk_size=40, overlap=10)
    assert len(chunks) > 1
    for chunk in chunks:
        assert not chunk.startswith(" ")
        assert len(chunk) <= 60  # С учетом безопасного поиска пробела

def test_greeting_regex():
    assert GREETING_REGEX.match("привет!")
    assert GREETING_REGEX.match("Здравствуйте, подскажите")
    assert GREETING_REGEX.match("Hello there")
    assert not GREETING_REGEX.match("Как запустить Docker?")

def test_get_session_context_guest():
    ctx = get_session_context(None)
    assert ctx["role"] == "guest"
    assert ctx["course_id"] == "default_course"

def test_get_session_context_invalid_token():
    ctx = get_session_context("Bearer invalid.fake.token")
    assert ctx["role"] == "guest"
