import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.chat import router as chat_router
from app.api.documents import router as doc_router
from app.api.lti import router as lti_router
from app.services.pdf_loader import load_and_chunk_file
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

@app.on_event("startup")
def startup():
    sample = os.path.join("data", "sample_git_guide.txt")
    if vector_store.count() == 0 and os.path.exists(sample):
        vector_store.add_chunks(load_and_chunk_file(sample))
        print("[AI-TUTOR] Базовая методичка по Git успешно загружена в базу!")

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
