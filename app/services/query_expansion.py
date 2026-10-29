"""LLM query expansion for weak retrieval results.

The fast path stays deterministic: expansion is only requested when the first
search returned no chunks at all and the query contains an abbreviation-like
token. This keeps off-topic and normal queries fast.
"""

import re
from typing import Dict, List

import httpx

from app.core.config import settings
from app.services.bm25 import has_abbreviation

EXPANSION_SYSTEM_PROMPT = """Ты — поисковый ассистент. Перепиши вопрос студента в 1–3 коротких поисковых запроса на том же языке.

Правила:
1. Раскрой аббревиатуры и сокращения, если их значение однозначно следует из вопроса.
2. Не добавляй факты, которых нет в вопросе.
3. Верни только поисковые запросы, каждый с новой строки, без нумерации и пояснений."""


def should_expand_query(query: str, chunks: List[Dict]) -> bool:
    if not query or not has_abbreviation(query):
        return False
    return not chunks


def parse_expanded_queries(raw: str, limit: int = 3) -> List[str]:
    queries: List[str] = []
    seen = set()
    for line in raw.splitlines():
        query = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        query = query.strip("\"'`«» ")
        if len(query) < 2 or len(query) > 300:
            continue
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(query)
        if len(queries) >= limit:
            break
    return queries


async def expand_query(question: str) -> List[str]:
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": EXPANSION_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 80,
            "num_ctx": 1024,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )
            if response.status_code != 200:
                return []
            content = response.json().get("message", {}).get("content", "")
            return parse_expanded_queries(content)
    except Exception:
        return []
