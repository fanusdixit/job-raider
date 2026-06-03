"""Runtime adapter registry (Epic 2 Story 2.2)."""

from __future__ import annotations

import requests

from job_raider.http_client import HttpClient
from job_raider.matching import build_source_context
from job_raider.models import SearchConfig, SourceConfig
from job_raider.sources.adapters import get_adapter
from job_raider.sources.html_selectors import HtmlSelectorsAdapter
from job_raider.sources.playwright_adapter import PlaywrightAdapter
from job_raider.sources.rss import RssAdapter


def test_get_adapter_html_selectors_fetch_minimal_html():
    a = get_adapter("html_selectors")
    assert isinstance(a, HtmlSelectorsAdapter)
    ctx = build_source_context(
        SearchConfig(id="x", name="X", keywords=("k",), sources=(), region=None),
        SourceConfig(
            "html_selectors",
            "Lab",
            {
                "url": "https://u",
                "item": "li",
                "title": "a",
                "link": "a",
            },
        ),
        a,
    )
    session = requests.Session()

    def fake_get(url, timeout=None):  # noqa: ARG001
        r = requests.Response()
        r.status_code = 200
        r._content = b"<ul><li><a href='https://u/1'>One</a></li></ul>"
        r.url = url
        return r

    session.get = fake_get  # type: ignore[method-assign]
    http = HttpClient(session=session, polite_delay_ms_range=(1, 1))
    items = a.fetch(ctx, http)
    assert len(items) == 1
    assert items[0].title == "One"


def test_get_adapter_returns_rss():
    assert isinstance(get_adapter("rss"), RssAdapter)


def test_get_adapter_returns_playwright():
    assert isinstance(get_adapter("playwright"), PlaywrightAdapter)
