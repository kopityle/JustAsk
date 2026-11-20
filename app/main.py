import asyncio
import os
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.chat import router as chat_router
from app.api.documents import router as doc_router
from app.api.lti import router as lti_router
from app.services.vector_store import vector_store

os.makedirs(settings.DOCS_DIR, exist_ok=True)

app = FastAPI(title=settings.PROJECT_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def allow_moodle_iframe(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "ALLOWALL"
    response.headers["Content-Security-Policy"] = "frame-ancestors *;"
    return response

@app.middleware("http")
async def limit_upload_request_size(request, call_next):
    if request.method == "POST" and request.url.path == "/api/documents/upload":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
            except ValueError:
                size = 0
            if size > settings.MAX_UPLOAD_SIZE + 1024 * 1024:
                return JSONResponse(status_code=413, content={"detail": "Файл слишком большой"})
    return await call_next(request)

app.include_router(chat_router)
app.include_router(doc_router)
app.include_router(lti_router)


@app.get("/health")
async def health():
    """Быстрая проверка зависимостей для systemd и Nginx."""
    chunks = None
    chroma_error = None
    try:
        chunks = await asyncio.to_thread(vector_store.count)
    except Exception as exc:
        chroma_error = f"ChromaDB недоступна: {exc}"

    ollama_status = "unavailable"
    ollama_error = None
    ollama_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=2.0) as ollama_client:
            ollama_response = await ollama_client.get(ollama_url)
            if ollama_response.status_code != 200:
                raise RuntimeError(f"HTTP {ollama_response.status_code}")
        ollama_status = "ok"
    except Exception as exc:
        ollama_error = f"Ollama недоступна: {exc}"

    errors = [error for error in (chroma_error, ollama_error) if error]
    if errors:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "chunks": chunks,
                "ollama": ollama_status,
                "errors": errors,
            },
        )

    return {"status": "ok", "chunks": chunks, "ollama": ollama_status}


@app.on_event("startup")
def startup():
    try:
        vector_store.embed_fn._get_model()
        print("[AI-TUTOR] Модель эмбеддингов FastEmbed прогрета.")
    except Exception as e:
        print(f"[AI-TUTOR] Не удалось прогреть модель эмбеддингов: {e}")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
