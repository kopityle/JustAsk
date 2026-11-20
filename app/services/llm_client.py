import httpx, json, os 
from typing import List, Dict, AsyncGenerator
from app.core.config import settings

SYSTEM_PROMPT = """Ты — академический ассистент по материалам курса.

Инструкции:
1. Отвечай на вопрос студента, опираясь только на переданные материалы курса. Разрешено перефразировать текст и выделять суть.
2. Не используй факты, которых нет в контексте. Если в материалах нет информации по теме вопроса, напиши только: "В материалах курса ответ на этот вопрос не найден."
3. Если в ответе есть примеры, код, формулы, обозначения, названия или цитаты, оформляй их аккуратно и единообразно.
4. Отвечай кратко, нейтрально, без приветствий и лишних вводных слов, строго на языке вопроса."""

async def stream_rag_answer(question: str, chunks: List[Dict], is_pure_greeting: bool = False) -> AsyncGenerator[str, None]:
    if is_pure_greeting:
        user_content = f"Студент обращается к тебе (поприветствуй на том же языке и предложи задать вопрос по курсу): {question}"
    elif chunks:
        context_blocks = [f"[{c['document']}, стр. {c['page']}]:\n{c['text']}" for c in chunks]
        context_text = "\n\n".join(context_blocks)
        user_content = f"Материалы курса:\n{context_text}\n\nВопрос студента: {question}"
    else:
        user_content = f"Материалы курса:\n[МАТЕРИАЛЫ ПО ДАННОМУ ВОПРОСУ В БАЗЕ ОТСУТСТВУЮТ]\n\nВопрос студента: {question}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0)
        ) as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 180,
                        "num_ctx": 1536,
                        "num_thread": max(1, os.cpu_count() or 4),       # Задействуем все доступные потоки процессора
                        "f16_kv": True,        # Половинная точность для экономии памяти
                        "use_mmap": True,       # Ускоренная загрузка из оперативной памяти
                        "repeat_penalty": 1.15,   # Лечит зацикливание модели
                        "repeat_last_n": 64
                    }
                }
            ) as response:
                if response.status_code != 200:
                    yield "Ошибка инференса локальной модели."
                    return

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if data.get("done", False):
                            break
                    except Exception:
                        continue
    except (httpx.HTTPError, Exception) as e:
        yield f"Ошибка при обращении к локальной модели Ollama: {e}"
