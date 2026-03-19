"""HttpClient retries, delays, User-Agent (Epic 2 Story 2.1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from job_raider import __version__
from job_raider.http_client import HttpClient, USER_AGENT


def test_user_agent_contains_version():
    assert __version__ in USER_AGENT
    assert "JobRaider" in USER_AGENT


def test_second_request_triggers_polite_delay():
    session = MagicMock()

    def ok_response(*_a, **_k):
        r = MagicMock()
        r.status_code = 200
        r.raise_for_status = MagicMock()
        return r

    session.get.side_effect = ok_response
    client = HttpClient(session=session, polite_delay_ms_range=(10, 10))
    with patch("job_raider.http_client.time.sleep") as sl:
        client.get("https://example.com/a")
        client.get("https://example.com/b")
    assert session.get.call_count == 2
    sl.assert_called_once()
    assert sl.call_args[0][0] == pytest.approx(0.01, rel=0.01)


def test_retries_on_503_then_success():
    session = MagicMock()
    bad = MagicMock()
    bad.status_code = 503
    bad.raise_for_status = MagicMock(side_effect=requests.HTTPError())
    good = MagicMock()
    good.status_code = 200
    good.raise_for_status = MagicMock()
    session.get.side_effect = [bad, bad, good]

    client = HttpClient(session=session, polite_delay_ms_range=(1, 1))
    with patch("job_raider.http_client.time.sleep"):
        r = client.get("https://example.com/feed")
    assert r is good
    assert session.get.call_count == 3


def test_connection_error_retry_then_success():
    session = MagicMock()
    good = MagicMock()
    good.status_code = 200
    good.raise_for_status = MagicMock()
    session.get.side_effect = [
        requests.ConnectionError("reset"),
        good,
    ]
    client = HttpClient(session=session, polite_delay_ms_range=(1, 1))
    with patch("job_raider.http_client.time.sleep"):
        r = client.get("https://example.com/x")
    assert r is good


def test_connection_error_exhausted_raises():
    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("fail")
    client = HttpClient(session=session, polite_delay_ms_range=(1, 1))
    with patch("job_raider.http_client.time.sleep"):
        with pytest.raises(requests.ConnectionError):
            client.get("https://example.com/x")
    assert session.get.call_count == 3


def test_session_get_receives_timeout():
    session = MagicMock()
    r = MagicMock()
    r.status_code = 200
    r.raise_for_status = MagicMock()
    session.get.return_value = r
    client = HttpClient(session=session, timeout=(12.5, 99.0), polite_delay_ms_range=(1, 1))
    with patch("job_raider.http_client.time.sleep"):
        client.get("https://a.test/u")
    session.get.assert_called_with("https://a.test/u", timeout=(12.5, 99.0))
