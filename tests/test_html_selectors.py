"""html_selectors adapter + fixtures (Epic 4)."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from job_raider.exceptions import AdapterError
from job_raider.http_client import HttpClient
from job_raider.matching import build_source_context
from job_raider.models import SearchConfig, SourceConfig
from job_raider.normalize import normalize_and_filter
from job_raider.sources.base import SourceContext
from job_raider.sources.html_selectors import HtmlSelectorsAdapter

FIX_ABS = Path(__file__).resolve().parent / "fixtures" / "listing_absolute.html"
FIX_REL = Path(__file__).resolve().parent / "fixtures" / "listing_relative.html"


def _http_with_bytes(content: bytes) -> HttpClient:
    session = requests.Session()

    def fake_get(url, timeout=None):  # noqa: ARG001
        r = requests.Response()
        r.status_code = 200
        r._content = content
        r.url = url
        return r

    session.get = fake_get  # type: ignore[method-assign]
    return HttpClient(session=session, polite_delay_ms_range=(1, 1))


def _ctx(
    *,
    params: dict,
    search_id: str = "s",
    search_name: str = "S",
    keywords: tuple[str, ...] = ("x",),
) -> SourceContext:
    search = SearchConfig(
        id=search_id,
        name=search_name,
        keywords=keywords,
        region=None,
        sources=(),
    )
    source = SourceConfig(
        adapter="html_selectors",
        label="HTML",
        params=params,
    )
    return build_source_context(search, source, HtmlSelectorsAdapter())


def test_html_absolute_fixture_two_items_with_dates():
    params = {
        "url": "https://example.com/list.html",
        "item": "article.job",
        "title": "h2 a",
        "link": "h2 a",
        "date": "time[datetime]",
    }
    ctx = _ctx(params=params)
    adapter = HtmlSelectorsAdapter()
    items = adapter.fetch(ctx, _http_with_bytes(FIX_ABS.read_bytes()))
    assert len(items) == 2
    titles = [i.title for i in items]
    assert "Ingegnere software Python" in titles
    assert "Comunicazione istituzionale" in titles
    py = next(i for i in items if "Python" in i.title)
    assert py.url == "https://corp.example/lavori/1"
    assert py.published_at is not None
    assert py.published_at.year == 2024
    assert py.published_at.month == 3
    comm = next(i for i in items if "Comunicazione" in i.title)
    assert comm.published_at is None


def test_html_relative_fixture_requires_link_base_for_normalize():
    params = {
        "url": "https://pa.example/bandi.html",
        "item": "div.post",
        "title": "a.title",
        "link": "a.title",
        "date": "span.when",
        "link_base": "https://pa.example",
    }
    ctx = _ctx(params=params, keywords=("PNRR",))
    adapter = HtmlSelectorsAdapter()
    items = adapter.fetch(ctx, _http_with_bytes(FIX_REL.read_bytes()))
    assert len(items) == 2
    assert items[0].url.startswith("/")
    opps = normalize_and_filter(items, ctx, keywords=ctx.expanded_keywords)
    assert len(opps) == 1
    assert opps[0].title == "Operatore PNRR — Lazio"
    assert opps[0].dedupe_id == "https://pa.example/bandi/2024/concorso-99"
    assert opps[0].published_at is not None
    assert opps[0].published_at.month == 6


def test_html_selectors_http_error():
    session = requests.Session()
    session.get = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[misc]
        requests.ConnectionError("down")
    )
    http = HttpClient(session=session, polite_delay_ms_range=(1, 1))
    ctx = _ctx(
        params={
            "url": "https://x/p",
            "item": "div",
            "title": "a",
            "link": "a",
        }
    )
    with pytest.raises(AdapterError, match="HTTP error"):
        HtmlSelectorsAdapter().fetch(ctx, http)


def test_html_selectors_invalid_item_selector():
    ctx = _ctx(
        params={
            "url": "https://x/p",
            "item": "a:not(",
            "title": "a",
            "link": "a",
        }
    )
    with pytest.raises(AdapterError, match="invalid CSS selector"):
        HtmlSelectorsAdapter().fetch(ctx, _http_with_bytes(b"<html></html>"))


def test_html_missing_url_param():
    ctx = _ctx(params={"item": "div", "title": "a", "link": "a"})
    with pytest.raises(AdapterError, match="url"):
        HtmlSelectorsAdapter().fetch(ctx, _http_with_bytes(b"<html></html>"))
