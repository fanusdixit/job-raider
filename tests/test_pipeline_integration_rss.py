"""
Integration-style pipeline test: real config → RSS adapter → merge → write (Epic 7 Story 7.2).

HTTP and robots.txt are mocked; no live network.
"""

from __future__ import annotations

import json
import textwrap
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

from job_raider.http_client import HttpClient
from job_raider import pipeline as pipeline_mod

FIXTURE_FEED = Path(__file__).resolve().parent / "fixtures" / "sample_feed.xml"


class _BytesReaderCM:
    """Minimal context manager for ``urllib.request.urlopen``."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _BytesReaderCM:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _url_str(url: str | urllib.request.Request) -> str:
    if isinstance(url, urllib.request.Request):
        return url.full_url
    return str(url)


def _urlopen_robots_allow_factory() -> MagicMock:
    def fake(url: str | urllib.request.Request, *a: object, **kw: object) -> _BytesReaderCM:
        u = _url_str(url)
        if u.endswith("/robots.txt"):
            return _BytesReaderCM(b"User-agent: *\nDisallow:\n")
        raise AssertionError(f"unexpected urlopen URL: {u!r}")

    m = MagicMock(side_effect=fake)
    return m


def test_pipeline_mocked_rss_writes_results_and_dashboard(tmp_path: Path) -> None:
    """Golden path: mocked robots allow + mocked GET returns fixture RSS XML."""
    feed_url = "https://jobs.example.com/feed.xml"
    cfg = tmp_path / "searches.yaml"
    cfg.write_text(
        textwrap.dedent(
            f"""
            searches:
              - id: integ
                name: "Integration search"
                keywords: [python]
                sources:
                  - adapter: rss
                    label: FixtureFeed
                    url: "{feed_url}"
            """
        ).strip(),
        encoding="utf-8",
    )
    results = tmp_path / "results.json"
    index = tmp_path / "index.html"
    xml_bytes = FIXTURE_FEED.read_bytes()

    session = MagicMock()

    def session_get(url: str, **_k: object) -> MagicMock:
        assert url == feed_url
        r = MagicMock()
        r.status_code = 200
        r.content = xml_bytes
        r.raise_for_status = MagicMock()
        return r

    session.get.side_effect = session_get
    http = HttpClient(session=session, polite_delay_ms_range=(1, 1))

    with (
        patch("urllib.request.urlopen", _urlopen_robots_allow_factory()),
        patch("job_raider.http_client.time.sleep"),
    ):
        code = pipeline_mod.run(
            config_path=cfg,
            results_path=results,
            index_path=index,
            http_client=http,
        )

    assert code == 0
    assert results.is_file()
    assert index.is_file()

    payload = json.loads(results.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["source_runs"] == [
        {
            "search_id": "integ",
            "search_name": "Integration search",
            "source_label": "FixtureFeed",
            "status": "ok",
            "item_count": 1,
            "error_detail": None,
        }
    ]
    blocks = {s["id"]: s for s in payload["searches"]}
    assert "integ" in blocks
    items = blocks["integ"]["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Python Developer in Rome"
    assert items[0]["url"] == "https://jobs.example.com/p/1"

    html_out = index.read_text(encoding="utf-8")
    assert "Integration search" in html_out
    assert "Python Developer in Rome" in html_out
    assert "https://jobs.example.com/p/1" in html_out
    assert '<details class="run-report">' in html_out
    assert "FixtureFeed" in html_out
    assert "run-report__status-ok" in html_out
    session.get.assert_called_once()


def test_pipeline_skips_rss_when_roots_disallow_all(tmp_path: Path) -> None:
    """Epic 7 Story 7.1: disallowed URL → no adapter GET; run still exits 0."""
    feed_url = "https://blocked.example/feed.xml"
    cfg = tmp_path / "searches.yaml"
    cfg.write_text(
        textwrap.dedent(
            f"""
            searches:
              - id: rb
                name: "Robots block"
                keywords: [x]
                sources:
                  - adapter: rss
                    label: BlockedFeed
                    url: "{feed_url}"
            """
        ).strip(),
        encoding="utf-8",
    )
    results = tmp_path / "results.json"
    index = tmp_path / "index.html"

    def fake_urlopen(url: str | urllib.request.Request, *a: object, **kw: object) -> _BytesReaderCM:
        u = _url_str(url)
        if u.endswith("/robots.txt"):
            return _BytesReaderCM(b"User-agent: *\nDisallow: /\n")
        raise AssertionError(f"unexpected urlopen URL: {u!r}")

    session = MagicMock()
    http = HttpClient(session=session, polite_delay_ms_range=(1, 1))

    with (
        patch("urllib.request.urlopen", MagicMock(side_effect=fake_urlopen)),
        patch("job_raider.http_client.time.sleep"),
    ):
        code = pipeline_mod.run(
            config_path=cfg,
            results_path=results,
            index_path=index,
            http_client=http,
        )

    assert code == 0
    session.get.assert_not_called()
    payload = json.loads(results.read_text(encoding="utf-8"))
    assert payload["searches"][0]["items"] == []
    assert payload["source_runs"][0]["status"] == "error"
    assert payload["source_runs"][0]["source_label"] == "BlockedFeed"
