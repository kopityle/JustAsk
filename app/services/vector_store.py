import os, threading, hashlib
from collections import defaultdict
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from fastembed import TextEmbedding
from app.core.config import settings
from app.services.bm25 import BM25Index, has_abbreviation, tokenize
from typing import List, Dict, Optional


def make_chunk_id(filename: str, course_id: str, page: int, chunk_idx: int) -> str:
    file_hash = hashlib.md5(filename.encode("utf-8")).hexdigest()[:8]
    return f"{file_hash}_{course_id}_p{page}_{chunk_idx}"

class FastEmbedFunction(EmbeddingFunction):
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._model_lock = threading.Lock()

    def name(self) -> str:
        return f"fastembed_{self.model_name}"

    def get_config(self) -> Dict:
        return {"model_name": self.model_name}

    def _get_model(self) -> TextEmbedding:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def __call__(self, input: Documents) -> Embeddings:
        return [vector.tolist() for vector in self._get_model().embed(input)]

class VectorStore:
    def __init__(self):
        os.makedirs(settings.CHROMA_DIR, exist_ok=True)
        self.client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
        
        self.embed_fn = FastEmbedFunction(model_name=settings.EMBED_MODEL)

        self.collection = self.client.get_or_create_collection(
            name="materials_v2",
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"}
        )

        self._rrf_k = 60
        self._bm25_cache: Dict[str, BM25Index] = {}
        self._bm25_lock = threading.Lock()

    def reset_collection(self) -> None:
        try:
            self.client.delete_collection("materials_v2")
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name="materials_v2",
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self._invalidate_bm25()

    def _invalidate_bm25(self) -> None:
        with self._bm25_lock:
            self._bm25_cache.clear()

    def _get_bm25(self, course_id: Optional[str]) -> BM25Index:
        course_key = course_id or "default_course"
        with self._bm25_lock:
            cached = self._bm25_cache.get(course_key)
            if cached is not None:
                return cached

            if course_key != "default_course":
                data = self.collection.get(
                    where={"course_id": course_key},
                    include=["documents", "metadatas"],
                )
            else:
                data = self.collection.get(include=["documents", "metadatas"])

            documents = data.get("documents") or []
            metadatas = data.get("metadatas") or []

            unique_documents = []
            unique_metadatas = []
            seen = set()
            for document, metadata in zip(documents, metadatas):
                metadata = metadata or {}
                key = (
                    metadata.get("document", "doc"),
                    metadata.get("page", 1),
                    document,
                )
                if key in seen:
                    continue
                seen.add(key)
                unique_documents.append(document)
                unique_metadatas.append(metadata)

            index = BM25Index()
            index.build(unique_documents, unique_metadatas)
            self._bm25_cache[course_key] = index
            return index

    def add_chunks(self, chunks: List[Dict], course_id: str = "default_course"):
        if not chunks:
            return

        # Индексируем пачками по 15 штук (защита от ReadTimeout)
        batch_size = 15
        total = len(chunks)
        chunk_index = defaultdict(int)
        self._invalidate_bm25()
        print(f"\n[INDEX] Начинаем загрузку книги: всего {total} чанков. Обрабатываем пачками по {batch_size}...")

        for i in range(0, total, batch_size):
            batch = chunks[i : i + batch_size]
            docs = [c["text"] for c in batch]
            metas = [
                {"document": c["document"], "page": int(c["page"]), "course_id": course_id}
                for c in batch
            ]
            ids = []
            for c in batch:
                page = int(c["page"])
                chunk_key = (c["document"], page)
                ids.append(make_chunk_id(c["document"], course_id, page, chunk_index[chunk_key]))
                chunk_index[chunk_key] += 1

            self.collection.upsert(documents=docs, metadatas=metas, ids=ids)
            print(f"[INDEX] Готово: {min(i + batch_size, total)}/{total}")

        print("[INDEX]  Книга успешно загружена и проиндексирована в векторную базу!\n")
        self._invalidate_bm25()

    def delete_document(self, filename: str, course_id: str = None) -> int:
        where_filter = {"document": filename}
        if course_id and course_id != "default_course":
            where_filter = {"$and": [{"document": filename}, {"course_id": course_id}]}
        
        data = self.collection.get(where=where_filter)
        ids_to_del = data.get("ids", [])
        if ids_to_del:
            self.collection.delete(ids=ids_to_del)
            self._invalidate_bm25()
        return len(ids_to_del)

    def delete_course(self, course_id: str = "default_course") -> int:
        course_key = course_id or "default_course"
        data = self.collection.get(where={"course_id": course_key})
        ids_to_del = data.get("ids", [])
        if ids_to_del:
            self.collection.delete(ids=ids_to_del)
            self._invalidate_bm25()
        return len(ids_to_del)

    def search(self, query: str, top_k: int = 4, course_id: str = None) -> List[Dict]:
        total = self.collection.count()
        if total == 0:
            return []

        course_key = course_id or "default_course"
        where_filter = {"course_id": course_key} if course_key != "default_course" else None
        candidate_count = min(max(top_k * 4, 20), total)

        res = self.collection.query(
            query_texts=[query],
            n_results=candidate_count,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )

        dense_ranked: List[Dict] = []
        if res and res.get("documents") and res["documents"][0]:
            seen_dense = set()
            for document, metadata, distance in zip(
                res["documents"][0],
                res["metadatas"][0],
                res["distances"][0],
            ):
                metadata = metadata or {}
                key = (
                    metadata.get("document", "doc"),
                    metadata.get("page", 1),
                    document,
                )
                if key in seen_dense:
                    continue
                if distance <= settings.DISTANCE_THRESHOLD:
                    seen_dense.add(key)
                    dense_ranked.append({
                        "text": document,
                        "document": metadata.get("document", "doc"),
                        "page": metadata.get("page", 1),
                        "course_id": metadata.get("course_id", course_key),
                        "distance": distance,
                    })

        bm25 = self._get_bm25(course_key)

        query_terms = set(tokenize(query))
        allow_single_match = len(query_terms) <= 1 or has_abbreviation(query)
        bm25_ranked: List[Dict] = []
        for idx, score in bm25.search(
            query,
            top_n=candidate_count,
            min_matched_terms=1 if allow_single_match else 2,
        ):
            metadata = bm25.metadatas[idx] or {}
            bm25_ranked.append({
                "text": bm25.documents[idx],
                "document": metadata.get("document", "doc"),
                "page": metadata.get("page", 1),
                "course_id": metadata.get("course_id", course_key),
                "distance": None,
                "bm25_score": score,
            })

        # Reciprocal Rank Fusion: merge the two independent rankings without
        # comparing incomparable score scales (cosine distance vs BM25).
        fused: Dict[tuple, Dict] = {}
        for rank, item in enumerate(dense_ranked, start=1):
            key = (item["document"], item["page"], item["text"])
            entry = fused.setdefault(key, {**item, "rrf_score": 0.0})
            entry["rrf_score"] += 1.0 / (self._rrf_k + rank)

        for rank, item in enumerate(bm25_ranked, start=1):
            key = (item["document"], item["page"], item["text"])
            entry = fused.get(key)
            if entry is None:
                entry = {**item, "rrf_score": 0.0}
                fused[key] = entry
            entry["bm25_score"] = item["bm25_score"]
            entry["rrf_score"] += 1.0 / (self._rrf_k + rank)

        ranked = sorted(
            fused.values(),
            key=lambda item: item["rrf_score"],
            reverse=True,
        )
        return ranked[:top_k]

    def count(self) -> int:
        return self.collection.count()

    def unique_count(self, course_id: str = None) -> int:
        return sum(item["chunks"] for item in self.get_document_stats(course_id))

    def get_document_stats(self, course_id: str = None) -> List[Dict]:
        if self.collection.count() == 0:
            return []
        
        where_filter = {"course_id": course_id} if (course_id and course_id != "default_course") else None
        if where_filter:
            data = self.collection.get(
                where=where_filter,
                include=["documents", "metadatas"],
            )
        else:
            data = self.collection.get(include=["documents", "metadatas"])

        docs_map = {}
        seen_chunks = set()
        for document, meta in zip(
            data.get("documents") or [],
            data.get("metadatas") or [],
        ):
            if not meta:
                continue
            name = meta.get("document", "unknown")
            page = meta.get("page", 1)
            key = (name, page, document)
            if key in seen_chunks:
                continue
            seen_chunks.add(key)
            if name not in docs_map:
                docs_map[name] = {"chunks": 0, "max_page": 1}
            docs_map[name]["chunks"] += 1
            if page > docs_map[name]["max_page"]:
                docs_map[name]["max_page"] = page
        
        return [{"filename": k, "chunks": v["chunks"], "pages": v["max_page"]} for k, v in docs_map.items()]

vector_store = VectorStore()
