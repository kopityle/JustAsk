from pydantic import BaseModel, Field
from typing import List, Optional

class SourceChunk(BaseModel):
    document: str
    page: int
    text: str

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)

class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceChunk]
    is_found: bool = True
    latency_ms: int = 0

class FeedbackRequest(BaseModel):
    question: str
    answer: str
    is_positive: bool
    event_id: Optional[str] = Field(default=None, max_length=64)
