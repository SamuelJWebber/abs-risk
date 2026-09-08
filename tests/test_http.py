from absrisk.http import make_session, user_agent


def test_user_agent_names_project():
    ua = user_agent()
    assert ua.startswith("absrisk/")
    assert "github.com/SamuelJWebber/abs-risk" in ua
    assert "Mozilla" not in ua


def test_session_carries_user_agent():
    s = make_session()
    assert s.headers["User-Agent"] == user_agent()
