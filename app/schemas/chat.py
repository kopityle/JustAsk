from pydantic import BaseModel
from typing import List, Optional

class SourceChunk(BaseModel):
    document: str
    page: int
    text: str

class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceChunk]
    is_found: bool = True
    latency_ms: int = 0

class FeedbackRequest(BaseModel):
    question: str
    answer: str
    is_positive: bool
