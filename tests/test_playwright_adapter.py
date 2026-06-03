"""playwright adapter + mocked browser (offline)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import requests

from job_raider.exceptions import AdapterError
from job_raider.http_client import HttpClient
from job_raider.matching import build_source_context
from job_raider.models import SearchConfig, SourceConfig
from job_raider.sources.base import SourceContext
from job_raider.sources.playwright_adapter import PlaywrightAdapter

FIX_ABS = Path(__file__).resolve().parent / "fixtures" / "listing_absolute.html"


def _http() -> HttpClient:
    return HttpClient(session=requests.Session(), polite_delay_ms_range=(1, 1))


def _ctx(*, params: dict) -> SourceContext:
    search = SearchConfig(
        id="s",
        name="S",
        keywords=("bando",),
        region=None,
        sources=(),
    )
    source = SourceConfig(
        adapter="playwright",
        label="Albo Pretorio",
        params=params,
    )
    return build_source_context(search, source, PlaywrightAdapter())


def _listing_params() -> dict:
    return {
        "url": "https://scuola.edu.it/albo",
        "item": "article.job",
        "title": "h2 a",
        "link": "h2 a",
        "date": "time[datetime]",
    }


@patch("job_raider.sources.playwright_adapter._PLAYWRIGHT_AVAILABLE", True)
@patch(
    "job_raider.sources.playwright_adapter._load_page_html",
    new_callable=AsyncMock,
)
def test_playwright_fixture_extracts_items(mock_load: AsyncMock) -> None:
    mock_load.return_value = FIX_ABS.read_text()
    ctx = _ctx(params=_listing_params())
    items = PlaywrightAdapter().fetch(ctx, _http())
    assert len(items) == 2
    assert any("Python" in i.title for i in items)
    mock_load.assert_awaited_once()


@patch("job_raider.sources.playwright_adapter._PLAYWRIGHT_AVAILABLE", True)
@patch(
    "job_raider.sources.playwright_adapter._load_page_html",
    new_callable=AsyncMock,
)
def test_playwright_navigation_error(mock_load: AsyncMock) -> None:
    from job_raider.sources import playwright_adapter as pa

    mock_load.side_effect = pa.PlaywrightError("timeout")
    ctx = _ctx(params=_listing_params())
    with pytest.raises(AdapterError, match="Playwright error"):
        PlaywrightAdapter().fetch(ctx, _http())


@patch("job_raider.sources.playwright_adapter._PLAYWRIGHT_AVAILABLE", False)
def test_playwright_not_installed_skips(caplog: pytest.LogCaptureFixture) -> None:
    ctx = _ctx(params=_listing_params())
    items = PlaywrightAdapter().fetch(ctx, _http())
    assert items == []
    assert any("playwright is not installed" in r.message for r in caplog.records)


@patch("job_raider.sources.playwright_adapter._PLAYWRIGHT_AVAILABLE", True)
@patch(
    "job_raider.sources.playwright_adapter._load_page_html",
    new_callable=AsyncMock,
)
def test_playwright_invalid_item_selector(mock_load: AsyncMock) -> None:
    mock_load.return_value = "<html></html>"
    params = {**_listing_params(), "item": "a:not("}
    ctx = _ctx(params=params)
    with pytest.raises(AdapterError, match="invalid CSS selector"):
        PlaywrightAdapter().fetch(ctx, _http())


def test_playwright_missing_url_param() -> None:
    ctx = _ctx(params={"item": "div", "title": "a", "link": "a"})
    with pytest.raises(AdapterError, match="url"):
        PlaywrightAdapter().fetch(ctx, _http())
