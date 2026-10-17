import pytest
from app.api.lti import _role_from_lti

def test_lti_launch_missing_params(client):
    # Запрос без OAuth параметров должен возвращать ошибку
    response = client.post("/api/lti/launch", data={})
    assert response.status_code in [400, 401, 404]

def test_lti_role_mapping_concept():
    # Проверка алгоритма маппинга ролей из Moodle
    assert _role_from_lti("Instructor,urn:lti:sysrole:ims/lis/Administrator") == "teacher"
    assert _role_from_lti("Learner") == "student"
    assert _role_from_lti("Student") == "student"