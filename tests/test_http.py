import os
from unittest import mock

from absrisk.http import make_session, user_agent


def test_user_agent_is_sec_plain_format():
    with mock.patch.dict(os.environ, {"ABSRISK_CONTACT": "someone@example.com", "ABSRISK_NAME": "Some Name"}):
        ua = user_agent()
    assert ua == "Some Name abs-risk/0.1.0 someone@example.com"
    assert "http" not in ua and "(" not in ua  # the SEC edge refuses a URL or parentheses in the User-Agent
    assert "Mozilla" not in ua


def test_user_agent_without_contact_still_names_project():
    with mock.patch.dict(os.environ, {"ABSRISK_CONTACT": "", "ABSRISK_NAME": ""}):
        assert user_agent() == "abs-risk/0.1.0"


def test_session_carries_user_agent():
    s = make_session()
    assert s.headers["User-Agent"] == user_agent()
