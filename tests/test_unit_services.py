import pytest
from app.core.config import settings
from app.services.pdf_loader import clean_pdf_text, load_and_chunk_file, split_text_clean
from app.services.vector_store import FastEmbedFunction, VectorStore
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

def test_load_and_chunk_docx(tmp_path):
    from docx import Document as DocxDocument

    path = tmp_path / "method.docx"
    document = DocxDocument()
    document.add_paragraph("Первый абзац методички.")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Задание"
    table.cell(0, 1).text = "Описание задания"
    document.add_heading("Раздел 2", level=1)
    document.add_paragraph("Второй абзац после заголовка.")
    document.save(str(path))

    chunks = load_and_chunk_file(str(path))
    assert chunks
    assert all(chunk["page"] >= 1 for chunk in chunks)
    joined = "\n".join(chunk["text"] for chunk in chunks)
    assert "Первый абзац" in joined
    assert "Задание" in joined
    assert "Второй абзац" in joined
    assert max(chunk["page"] for chunk in chunks) >= 2


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


def test_default_course_is_strictly_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setattr(
        FastEmbedFunction,
        "__call__",
        lambda self, input: [[1.0, 0.0] for _ in input],
    )
    store = VectorStore()
    store.add_chunks(
        [{"document": "other.pdf", "page": 1, "text": "секретные данные другого курса"}],
        course_id="other_course",
    )
    store.add_chunks(
        [{"document": "default.pdf", "page": 1, "text": "обычные данные курса"}],
        course_id="default_course",
    )

    hits = store.search("секретные данные другого курса", top_k=4, course_id="default_course")
    assert hits
    assert all(hit["document"] == "default.pdf" for hit in hits)

    stats = store.get_document_stats(course_id="default_course")
    assert [item["filename"] for item in stats] == ["default.pdf"]

    assert store.delete_document("other.pdf", course_id="default_course") == 0
    remaining = store.collection.get(where={"course_id": "other_course"}, include=[])
    assert len(remaining["ids"]) == 1

    assert store.delete_document("other.pdf", course_id="other_course") == 1
