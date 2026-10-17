import os, re
import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException, Header
from app.core.config import settings
from app.services.pdf_loader import load_and_chunk_file
from app.services.vector_store import vector_store
from app.api.chat import get_session_context

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".txt"}
WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def can_manage_documents(session: dict) -> bool:
    role = session.get("role", "guest")
    return role == "teacher" or (role == "guest" and settings.ALLOW_GUEST_WRITES)


def require_manage_permission(session: dict, detail: str):
    if not can_manage_documents(session):
        raise HTTPException(status_code=403, detail=detail)


def validate_filename(filename: str) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Имя файла не указано")
    if (
        filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
        or filename != os.path.basename(filename)
    ):
        raise HTTPException(status_code=400, detail="Некорректное имя файла")
    if len(filename) > 200:
        raise HTTPException(status_code=400, detail="Слишком длинное имя файла")
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', filename):
        raise HTTPException(status_code=400, detail="Некорректное имя файла")

    stem, ext = os.path.splitext(filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Формат не поддерживается")
    if not stem or stem.lower() in WINDOWS_RESERVED_NAMES:
        raise HTTPException(status_code=400, detail="Некорректное имя файла")
    return filename


@router.get("")
def get_documents_info(authorization: str = Header(None)):
    session = get_session_context(authorization)
    course_id = session.get("course_id", "default_course")
    role = session.get("role", "guest")
    return {
        "documents": vector_store.get_document_stats(course_id=course_id),
        "total_chunks": vector_store.unique_count(course_id=course_id),
        "can_manage": can_manage_documents(session),
        "dev_write_access": role == "guest" and settings.ALLOW_GUEST_WRITES,
    }


def save_file(file: UploadFile, path: str) -> int:
    total = 0
    try:
        with open(path, "wb") as f:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="Файл слишком большой")
                f.write(chunk)
    except Exception:
        if os.path.exists(path):
            os.remove(path)
        raise
    return total


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), authorization: str = Header(None)):
    session = get_session_context(authorization)
    require_manage_permission(session, "Загрузка доступна только преподавателю")

    filename = validate_filename(file.filename)
    course_id = session.get("course_id", "default_course")
    os.makedirs(settings.DOCS_DIR, exist_ok=True)
    path = os.path.join(settings.DOCS_DIR, filename)

    if os.path.exists(path):
        raise HTTPException(
            status_code=409,
            detail="Файл с таким именем уже загружен. Удалите его перед повторной загрузкой.",
        )

    try:
        await asyncio.to_thread(save_file, file, path)
        chunks = await asyncio.to_thread(load_and_chunk_file, path)
        if not chunks:
            raise HTTPException(status_code=400, detail="В файле не найден текст для индексации")
        await asyncio.to_thread(vector_store.delete_document, filename, course_id)
        await asyncio.to_thread(vector_store.add_chunks, chunks, course_id=course_id)
    except Exception:
        await asyncio.to_thread(vector_store.delete_document, filename, course_id)
        if os.path.exists(path):
            os.remove(path)
        raise

    return {"status": "ok", "filename": filename, "indexed_chunks": len(chunks)}


@router.delete("/{filename}")
def delete_document(filename: str, authorization: str = Header(None)):
    session = get_session_context(authorization)
    require_manage_permission(session, "Удаление доступно только преподавателю")

    filename = validate_filename(filename)
    course_id = session.get("course_id", "default_course")
    removed_chunks = vector_store.delete_document(filename, course_id=course_id)
    file_path = os.path.join(settings.DOCS_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    elif removed_chunks == 0:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return {"status": "deleted", "filename": filename, "removed_chunks": removed_chunks}
