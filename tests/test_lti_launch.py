import pytest
from app.api.lti import _build_course_id, _role_from_lti

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