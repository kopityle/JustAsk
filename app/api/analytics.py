from fastapi import APIRouter, Header, HTTPException

from app.api.chat import get_session_context
from app.api.documents import safe_course_id
from app.services.analytics_store import get_course_summary, reset_course_analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _teacher_course_id(authorization: str | None) -> str:
    session = get_session_context(authorization)
    # Нарочно строгая проверка: can_manage_documents() пускает гостей с DEV-флагом.
    if session.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Статистика доступна только преподавателю")
    return safe_course_id(session.get("course_id"))


@router.get("/summary")
def analytics_summary(authorization: str = Header(None)):
    return get_course_summary(_teacher_course_id(authorization))


@router.delete("/summary")
def reset_analytics_summary(authorization: str = Header(None)):
    reset_course_analytics(_teacher_course_id(authorization))
    return {"status": "ok"}
