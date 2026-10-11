import asyncio, json, os, jwt, re, threading
from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, FeedbackRequest
from app.core.config import settings
from app.core.limiter import inference_semaphore
from app.services.vector_store import vector_store
from app.services.llm_client import stream_rag_answer
from app.services.query_expansion import expand_query, should_expand_query

router = APIRouter(prefix="/api", tags=["chat"])
JWT_SECRET = settings.JWT_SECRET
file_lock = threading.Lock()

GREETING_REGEX = re.compile(
    r'^(привет(ик)?|здравствуй(те)?|добр(ый|ое) (день|вечер|утро)|хай|хей|hello|hi|ку)\b[,\s!.]*', 
    flags=re.IGNORECASE
)

def dedupe_chunks(chunks: list, limit: int = 4) -> list:
    seen = set()
    unique = []
    for chunk in chunks:
        key = (chunk["document"], chunk["page"], chunk["text"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
        if len(unique) >= limit:
            break
    return unique


def get_session_context(authorization: str = None) -> dict:
    if not authorization:
        return {"role": "guest", "course_id": "default_course", "name": "Гость"}
    try:
        token = authorization.replace("Bearer ", "").strip()
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except Exception:
        return {"role": "guest", "course_id": "default_course", "name": "Гость"}

@router.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest, request: Request, authorization: str = Header(None)):
    raw_question = req.question.strip()
    if not raw_question:
        raise HTTPException(status_code=400, detail="Вопрос пуст")

    session = get_session_context(authorization)
    course_id = session.get("course_id", "default_course")

    clean_search_query = GREETING_REGEX.sub('', raw_question).strip()
    is_pure_greeting = len(clean_search_query) < 2

    chunks = []
    sources = []

    if not is_pure_greeting:
        chunks = await asyncio.to_thread(vector_store.search, clean_search_query, top_k=4, course_id=course_id)

        # Тяжёлое расширение — только если первый поиск вернул 0 результатов
        # и в вопросе есть аббревиатура (например, 1НФ).
        if should_expand_query(clean_search_query, chunks):
            try:
                expanded_queries = await asyncio.wait_for(expand_query(clean_search_query), timeout=15.0)
            except asyncio.TimeoutError:
                expanded_queries = []

            expanded_chunks = []
            for expanded_query in expanded_queries:
                expanded_chunks.extend(
                    await asyncio.to_thread(
                        vector_store.search,
                        expanded_query,
                        top_k=4,
                        course_id=course_id,
                    )
                )

            if expanded_chunks:
                chunks = dedupe_chunks(expanded_chunks + chunks)
            else:
                chunks = dedupe_chunks(chunks)

        # Моментальный отказ за 15 мс (оффтоп/борщ), без захода в семафор и вызова LLM
        if not chunks:
            async def fast_reject_stream():
                yield f"data: {json.dumps({'type': 'meta', 'sources': [], 'is_found': False}, ensure_ascii=False)}\n\n"
                msg = "В материалах курса ответ на этот вопрос не найден."
                yield f"data: {json.dumps({'type': 'token', 'token': msg}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(fast_reject_stream(), media_type="text/event-stream")

        seen_pages = set()
        for c in chunks:
            key = (c["document"], c["page"])
            if key not in seen_pages:
                seen_pages.add(key)
                sources.append({"document": c["document"], "page": c["page"], "text": c["text"]})

    async def event_generator():
        try:
            # Ждем свободный слот не дольше 25 секунд
            await asyncio.wait_for(inference_semaphore.acquire(), timeout=40.0)
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'token', 'token': '⚠️ Сервер сейчас перегружен большим количеством вопросов. Пожалуйста, повторите попытку через минуту.'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            initial_payload = {
                "type": "meta",
                "sources": sources,
                "is_found": is_pure_greeting or len(chunks) > 0
            }
            yield f"data: {json.dumps(initial_payload, ensure_ascii=False)}\n\n"

            async for token in stream_rag_answer(raw_question, chunks, is_pure_greeting):
                # ЕСЛИ КЛИЕНТ ЗАКРЫЛ ВКЛАДКУ — МГНОВЕННО ПРЕРЫВАЕМ ИНФЕРЕНС:
                if await request.is_disconnected():
                    print("[SSE] Клиент отключился, освобождаем видеопамять.")
                    break
                yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"
        finally:
            inference_semaphore.release()

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    os.makedirs(os.path.dirname(settings.FEEDBACK_FILE), exist_ok=True)
    with file_lock:  # Никаких наложений строк
        with open(settings.FEEDBACK_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(req.model_dump(), ensure_ascii=False) + "\n")
    return {"status": "recorded"}
