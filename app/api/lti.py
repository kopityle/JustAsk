import os
from urllib.parse import urlencode
import jwt
import time
from collections import OrderedDict
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from oauthlib.oauth1 import RequestValidator, SignatureOnlyEndpoint
from app.core.config import settings

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

router = APIRouter(prefix="/api/lti", tags=["lti"])

class LTIRequestValidator(RequestValidator):
    def __init__(self):
        self._nonce_store = OrderedDict()
        self._last_cleanup = time.time()

    @property
    def client_key_length(self):
        return 1, 255

    @property
    def nonce_length(self):
        return 1, 255

    @property
    def dummy_client(self):
        return "dummy"

    def get_client_secret(self, client_key, request):
        if client_key == settings.LTI_CONSUMER_KEY:
            return settings.LTI_SHARED_SECRET
        return "dummy"

    def validate_client_key(self, client_key, request):
        return client_key == settings.LTI_CONSUMER_KEY

    def validate_timestamp_and_nonce(self, client_key, timestamp, nonce, request, request_token=None, access_token=None):
        current_time = time.time()
        try:
            timestamp = float(timestamp)
        except (ValueError, TypeError):
            return False

        # Проверяем временную метку
        if abs(current_time - timestamp) > 300:  # 300 секунд = 5 минут
            return False

        # Проверяем nonce на Replay-атаку
        now_key = (client_key, timestamp, nonce)
        if now_key in self._nonce_store:
            return False
        self._nonce_store[now_key] = current_time

        # Очищаем старые записи
        if current_time - self._last_cleanup > 60:  # Очищаем каждую минуту
            self._last_cleanup = current_time
            cutoff = current_time - 300  # Удаляем записи старше 300 секунд
            self._nonce_store = OrderedDict(
                (k, v) for k, v in self._nonce_store.items() if v >= cutoff
            )

        return True

_endpoint = SignatureOnlyEndpoint(LTIRequestValidator())

def _role_from_lti(roles: str) -> str:
    roles_lower = (roles or "").lower()
    if any(r in roles_lower for r in ["instructor", "teacher", "administrator"]):
        return "teacher"
    return "student"

@router.post("/launch")
async def lti_launch(request: Request):
    body = (await request.body()).decode("utf-8")
    form = await request.form()
    # OAuthlib ожидает словарь, где значения - строки
    form_dict = {key: str(value) for key, value in form.items()}

    # КЛЮЧЕВОЙ МОМЕНТ:
    # Moodle подписывает запрос на HTTPS адрес, даже если внутренне туннель HTTP
    # Берем хост из заголовка, который передал Cloudflare
    proto = "https"
    host = request.headers.get("host")
    public_uri = f"{proto}://{host}{request.url.path}"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # Валидация (передаем сырой body, а не закодированный)
    valid, _ = _endpoint.validate_request(
        public_uri,
        http_method="POST",
        body=body,  # Используем сырой body
        headers=headers,
    )

    if not valid:
        print(f"DEBUG: Подпись не сошлась. Ожидаемый URI: {public_uri}")
        raise HTTPException(status_code=401, detail="Неверная цифровая подпись LTI")

    # Извлекаем роль и данные пользователя
    role = _role_from_lti(form_dict.get("roles", ""))
    course_id = form_dict.get("context_id") or "default_course"
    name = form_dict.get("lis_person_name_full") or "Пользователь Moodle"

    # Выпускаем JWT токен сессии
    token = jwt.encode(
        {"name": name, "role": role, "course_id": course_id},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    return RedirectResponse(url=f"/?token={token}", status_code=302)
