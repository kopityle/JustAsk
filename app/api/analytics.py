from fastapi import APIRouter, Header, HTTPException

from app.api.chat import get_session_context
from app.api.documents import safe_course_id
from app.services.analytics_store import get_course_summary

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def analytics_summary(authorization: str = Header(None)):
    session = get_session_context(authorization)
    # Нарочно строгая проверка: can_manage_documents() пускает гостей с DEV-флагом.
    if session.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Статистика доступна только преподавателю")

    course_id = safe_course_id(session.get("course_id"))
    return get_course_summary(course_id)
