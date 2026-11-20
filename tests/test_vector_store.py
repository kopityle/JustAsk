from unittest.mock import Mock

import pytest

from app.core.config import settings
from app.services.vector_store import FastEmbedFunction, VectorStore


def _chunks(*texts, document="material.pdf"):
    return [
        {"document": document, "page": page, "text": text}
        for page, text in enumerate(texts, start=1)
    ]


def _make_store(tmp_path, monkeypatch, embedder):
    monkeypatch.setattr(settings, "CHROMA_DIR", str(tmp_path / "chroma"))

    def patched_call(self, input):
        return embedder(input)

    # Chroma валидирует сигнатуру __call__: (self, input).
    monkeypatch.setattr(FastEmbedFunction, "__call__", patched_call)
    return VectorStore()


def test_search_applies_distance_threshold(tmp_path, monkeypatch):
    def embedder(texts):
        vectors = []
        for text in texts:
            lowered = text.lower()
            if "база данных" in lowered:
                vectors.append([1.0, 0.0, 0.0, 0.0])
            elif "сеть" in lowered:
                vectors.append([0.0, 1.0, 0.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0, 0.0])
        return vectors

    store = _make_store(tmp_path, monkeypatch, embedder)
    monkeypatch.setattr(settings, "DISTANCE_THRESHOLD", 0.50)
    store.add_chunks(
        _chunks("база данных", "компьютерная сеть", "алгоритм сортировки"),
        course_id="course_a",
    )

    results = store.search("база данных", top_k=4, course_id="course_a")

    # Ортогональные векторы имеют distance=1 > 0.50 и отсекаются.
    assert len(results) == 1
    assert results[0]["text"] == "база данных"
    assert results[0]["distance"] == pytest.approx(0.0)
    # И dense, и BM25 дали этот чанк первым.
    assert results[0]["rrf_score"] == pytest.approx(2 / 61)


def test_rrf_combines_dense_and_bm25_rankings(tmp_path, monkeypatch):
    def embedder(texts):
        vectors = []
        for text in texts:
            lowered = text.strip().lower()
            if lowered == "база данных":
                vectors.append([1.0, 0.0, 0.0, 0.0])  # вектор запроса
            elif lowered.startswith("база данных"):
                vectors.append([1.0, 1.0, 0.0, 0.0])  # BM25-лидер, плотный результат вторым
            else:
                vectors.append([1.0, 0.0, 0.0, 0.0])  # dense-лидер, BM25 его не знает
        return vectors

    store = _make_store(tmp_path, monkeypatch, embedder)
    monkeypatch.setattr(settings, "DISTANCE_THRESHOLD", 0.50)
    store.add_chunks(
        [
            {"document": "bm25.pdf", "page": 1, "text": "база данных курс"},
            {"document": "dense.pdf", "page": 1, "text": "совсем другой текст"},
        ],
        course_id="course_a",
    )

    results = store.search("база данных", top_k=4, course_id="course_a")

    assert [item["document"] for item in results] == ["bm25.pdf", "dense.pdf"]
    assert results[0]["rrf_score"] > results[1]["rrf_score"]
    assert results[0]["bm25_score"] > 0
    assert results[0]["rrf_score"] == pytest.approx(1 / 61 + 1 / 62)


def test_add_chunks_batches_more_than_15_chunks(tmp_path, monkeypatch):
    def embedder(texts):
        return [[1.0, float(index % 3 + 1), 0.0, 0.0] for index, _ in enumerate(texts)]

    store = _make_store(tmp_path, monkeypatch, embedder)
    upsert = Mock()
    monkeypatch.setattr(store.collection, "upsert", upsert)

    store.add_chunks(_chunks(*[f"текст {index}" for index in range(20)]), course_id="course_a")

    assert upsert.call_count == 2
    assert [len(call.kwargs["documents"]) for call in upsert.call_args_list] == [15, 5]
    for call in upsert.call_args_list:
        assert len(call.kwargs["ids"]) == len(set(call.kwargs["ids"]))
        assert all(meta["course_id"] == "course_a" for meta in call.kwargs["metadatas"])


def test_bm25_cache_evicts_least_recently_used_course(tmp_path, monkeypatch):
    store = _make_store(
        tmp_path,
        monkeypatch,
        lambda texts: [[1.0, 0.0, 0.0, 0.0] for _ in texts],
    )

    for index in range(20):
        store._get_bm25(f"course_{index}")
    assert len(store._bm25_cache) == 20

    # Обращение к course_0 обновляет его позицию, поэтому вытесняется course_1.
    store._get_bm25("course_0")
    store._get_bm25("course_20")

    assert len(store._bm25_cache) == 20
    assert "course_1" not in store._bm25_cache
    assert "course_0" in store._bm25_cache
    assert "course_20" in store._bm25_cache
    assert list(store._bm25_cache)[-1] == "course_20"


def test_document_stats_reads_only_metadata(tmp_path, monkeypatch):
    store = _make_store(
        tmp_path,
        monkeypatch,
        lambda texts: [[1.0, 0.0, 0.0, 0.0] for _ in texts],
    )
    original_get = store.collection.get

    def tracking_get(*args, **kwargs):
        assert kwargs["include"] == ["metadatas"]
        result = original_get(*args, **kwargs)
        assert not result.get("documents")
        return result

    monkeypatch.setattr(store.collection, "get", tracking_get)
    store.add_chunks(
        [
            {"document": "a.pdf", "page": 1, "text": "первый"},
            {"document": "a.pdf", "page": 1, "text": "второй"},
            {"document": "a.pdf", "page": 2, "text": "третий"},
        ],
        course_id="course_a",
    )

    stats = store.get_document_stats(course_id="course_a")

    assert stats == [{"filename": "a.pdf", "chunks": 3, "pages": 2}]
