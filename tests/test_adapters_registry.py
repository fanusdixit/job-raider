"""Runtime adapter registry (Epic 2 Story 2.2)."""

from __future__ import annotations

import pytest

from job_raider.exceptions import AdapterError
from job_raider.http_client import HttpClient
from job_raider.matching import build_source_context
from job_raider.models import SearchConfig, SourceConfig
from job_raider.sources.adapters import get_adapter
from job_raider.sources.html_selectors import HtmlSelectorsAdapter
from job_raider.sources.rss import RssAdapter


def test_get_adapter_html_selectors_is_stub():
    a = get_adapter("html_selectors")
    assert isinstance(a, HtmlSelectorsAdapter)
    ctx = build_source_context(
        SearchConfig(id="x", name="X", keywords=("k",), sources=(), region=None),
        SourceConfig("html_selectors", "Lab", {"url": "https://u", "item": "div", "title": "a", "link": "a"}),
        a,
    )
    http = HttpClient(polite_delay_ms_range=(1, 1))
    with pytest.raises(AdapterError, match="Epic 4"):
        a.fetch(ctx, http)


def test_get_adapter_returns_rss():
    assert isinstance(get_adapter("rss"), RssAdapter)
