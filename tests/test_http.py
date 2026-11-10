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


def test_rate_per_process_can_be_lowered_never_raised():
    from absrisk.http import MIN_INTERVAL, min_interval

    with mock.patch.dict(os.environ, {"ABSRISK_MAX_RPS": ""}):
        assert min_interval() == MIN_INTERVAL == 0.2
    with mock.patch.dict(os.environ, {"ABSRISK_MAX_RPS": "2.5"}):
        assert min_interval() == 0.4
        assert make_session().get_adapter("https://www.sec.gov").interval == 0.4
    with mock.patch.dict(os.environ, {"ABSRISK_MAX_RPS": "20"}):
        assert min_interval() == 0.2


def test_parallel_autos_jobs_share_the_project_rate():
    """REVIEW.md R2-12: four jobs at 5 a second each could reach 20 a second under one User-Agent."""
    from pathlib import Path

    import yaml

    from absrisk.http import MAX_RPS

    wf = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github" / "workflows" / "autos-build.yml").read_text(
        encoding="utf-8"))
    job = wf["jobs"]["build"]
    parallel = int(job["strategy"]["max-parallel"])
    fetch = [s for s in job["steps"] if "autos fetch" in str(s.get("run", ""))]
    assert len(fetch) == 1
    rps = float(fetch[0]["env"]["ABSRISK_MAX_RPS"])
    assert parallel * min(rps, MAX_RPS) <= MAX_RPS
