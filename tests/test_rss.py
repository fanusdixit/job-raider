"""RSS adapter offline tests (Epic 2 Story 2.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_raider.exceptions import AdapterError
from job_raider.http_client import HttpClient
from job_raider.matching import build_source_context
from job_raider.models import SearchConfig, SourceConfig
from job_raider.normalize import normalize_and_filter
from job_raider.sources.adapters import get_adapter
from job_raider.sources.rss import RssAdapter


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_feed.xml"


def _http_with_bytes(content: bytes) -> HttpClient:
    import requests

    session = requests.Session()

    def fake_get(url, timeout=None):  # noqa: ARG001
        r = requests.Response()
        r.status_code = 200
        r._content = content
        r.url = url
        return r

    session.get = fake_get  # type: ignore[method-assign]
    return HttpClient(session=session, polite_delay_ms_range=(1, 1))


def test_get_adapter_rss():
    a = get_adapter("rss")
    assert isinstance(a, RssAdapter)


def test_rss_fetch_maps_entries():
    body = FIXTURE.read_bytes()
    http = _http_with_bytes(body)
    search = SearchConfig(
        id="job",
        name="Jobs",
        keywords=("python",),
        region=None,
        sources=(),
    )
    source = SourceConfig(
        adapter="rss",
        label="Fixture",
        params={"url": "https://feeds.example/jobs.xml"},
    )
    ctx = build_source_context(search, source, RssAdapter())
    adapter = RssAdapter()
    items = adapter.fetch(ctx, http)
    titles = {i.title for i in items}
    assert "Python Developer in Rome" in titles
    assert "Java Engineer" in titles
    assert "Relative posting" in titles
    assert len(items) == 3


def test_rss_adapter_error_on_http_failure():
    import requests

    session = requests.Session()

    def boom(*_a, **_k):
        raise requests.ConnectionError("nope")

    session.get = boom  # type: ignore[method-assign]
    http = HttpClient(session=session, polite_delay_ms_range=(1, 1))
    ctx = build_source_context(
        SearchConfig(id="a", name="A", keywords=("k",), sources=(), region=None),
        SourceConfig("rss", "X", {"url": "https://x"}),
        RssAdapter(),
    )
    with pytest.raises(AdapterError, match="HTTP error"):
        RssAdapter().fetch(ctx, http)


def test_normalize_and_filter_or_keyword():
    body = FIXTURE.read_bytes()
    http = _http_with_bytes(body)
    search = SearchConfig(
        id="job",
        name="Jobs",
        keywords=("python",),
        region=None,
        sources=(),
    )
    source = SourceConfig(
        adapter="rss",
        label="Fixture",
        params={
            "url": "https://feeds.example/jobs.xml",
            "link_base": "https://jobs.example.com",
        },
    )
    adapter = RssAdapter()
    ctx = build_source_context(search, source, adapter)
    raws = adapter.fetch(ctx, http)
    opps = normalize_and_filter(raws, ctx, keywords=ctx.expanded_keywords)
    assert len(opps) == 1
    assert opps[0].title == "Python Developer in Rome"
    assert opps[0].dedupe_id == "https://jobs.example.com/p/1"
