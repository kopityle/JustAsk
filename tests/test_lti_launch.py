import time
import uuid
from urllib.parse import parse_qs, urlparse

import jwt
from oauthlib.oauth1 import Client, SIGNATURE_TYPE_BODY

from app.api.lti import _build_course_id, _role_from_lti
from app.core.config import settings


LTI_LAUNCH_URL = "https://testserver/api/lti/launch"


def _signed_lti_body(nonce=None, timestamp=None, **overrides):
    """Подписываем LTI-параметры как это делает Moodle (OAuth1, POST_BODY)."""
    params = {
        "context_id": "course_test",
        "resource_link_id": "link_1",
        "roles": "Instructor",
        "lis_person_name_full": "Иван Преподаватель",
    }
    params.update(overrides)
    client = Client(
        settings.LTI_CONSUMER_KEY,
        client_secret=settings.LTI_SHARED_SECRET,
        signature_type=SIGNATURE_TYPE_BODY,
        nonce=nonce or uuid.uuid4().hex,
        timestamp=str(int(time.time()) if timestamp is None else timestamp),
    )
    _, headers, body = client.sign(
        LTI_LAUNCH_URL,
        http_method="POST",
        body=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return body, headers


def _post_signed_launch(client, body, headers):
    return client.post(
        "/api/lti/launch",
        content=body,
        headers={**headers, "X-Forwarded-Proto": "https"},
        follow_redirects=False,
    )


def test_lti_launch_missing_params(client):
    # Запрос без OAuth параметров должен возвращать ошибку
    response = client.post("/api/lti/launch", data={})
    assert response.status_code in [400, 401, 404]


def test_lti_role_mapping_concept():
    # Проверка алгоритма маппинга ролей из Moodle
    assert _role_from_lti("Instructor,urn:lti:sysrole:ims/lis/Administrator") == "teacher"
    assert _role_from_lti("Learner") == "student"
    assert _role_from_lti("Student") == "student"


def test_lti_course_id_with_resource_link():
    assert _build_course_id("course-1", "link-2") == "course-1_link-2"
    assert _build_course_id("", "only-link") == "only-link"


def test_lti_course_id_without_resource_link():
    assert _build_course_id("course-1", "") == "course-1"
    assert _build_course_id(None, None) == "default_course"


def test_lti_course_id_sanitizes_special_characters():
    course_id = _build_course_id("../Course 1", "link/2?x=1")
    assert course_id == "___Course_1_link_2_x_1"
    assert "/" not in course_id
    assert ".." not in course_id


def test_lti_launch_with_valid_oauth_signature_issues_jwt(client):
    # Реальный ключ из конфигурации содержит подчёркивание.
    assert "_" in settings.LTI_CONSUMER_KEY
    body, headers = _signed_lti_body()

    response = _post_signed_launch(client, body, headers)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("/?token=")
    token = parse_qs(urlparse(location).query)["token"][0]
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    assert payload["role"] == "teacher"
    assert payload["course_id"] == "course_test_link_1"
    assert payload["name"] == "Иван Преподаватель"


def test_lti_launch_rejects_replayed_nonce(client):
    nonce = f"replay-{uuid.uuid4().hex}"
    body, headers = _signed_lti_body(nonce=nonce)

    assert _post_signed_launch(client, body, headers).status_code == 302
    assert _post_signed_launch(client, body, headers).status_code == 401


def test_lti_launch_rejects_expired_timestamp(client):
    body, headers = _signed_lti_body(timestamp=int(time.time()) - 400)

    response = _post_signed_launch(client, body, headers)

    assert response.status_code == 401
