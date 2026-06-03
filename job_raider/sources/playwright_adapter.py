"""
Playwright adapter: headless Chromium + CSS selectors (JS-rendered school sites).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

from job_raider.exceptions import AdapterError
from job_raider.http_client import USER_AGENT
from job_raider.models import RawItem
from job_raider.sources.base import SourceContext
from job_raider.sources.html_selectors import _extract_items

if TYPE_CHECKING:
    from job_raider.http_client import HttpClient

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

    class PlaywrightError(Exception):  # noqa: N818 — stub when playwright missing
        """Placeholder when playwright is not installed."""


def _require_param(params: dict, key: str, label: str) -> str:
    raw = params.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise AdapterError(f"{label}: playwright param {key!r} must be a non-empty string")
    return raw.strip()


def _timeout_ms(http: HttpClient) -> int:
    timeout = http._timeout
    if isinstance(timeout, tuple):
        return int(max(timeout) * 1000)
    return int(timeout * 1000)


async def _load_page_html(
    url: str,
    *,
    item_selector: str,
    timeout_ms: int,
    user_agent: str,
) -> str:
    """Launch headless Chromium, wait for listing items, return rendered HTML."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(user_agent=user_agent)
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_selector(item_selector, timeout=timeout_ms)
            return await page.content()
        finally:
            await browser.close()


def _parse_params(ctx: SourceContext) -> tuple[str, str, str, str, str | None]:
    params = ctx.params
    label = ctx.source_label
    url = _require_param(params, "url", label)
    item_sel = _require_param(params, "item", label)
    title_sel = _require_param(params, "title", label)
    link_sel = _require_param(params, "link", label)
    date_sel_raw = params.get("date")
    date_sel: str | None = None
    if date_sel_raw is not None:
        if not isinstance(date_sel_raw, str) or not date_sel_raw.strip():
            raise AdapterError(f"{label}: date must be a non-empty string when set")
        date_sel = date_sel_raw.strip()
    return url, item_sel, title_sel, link_sel, date_sel


class PlaywrightAdapter:
    """Fetch JS-rendered HTML listings via headless Chromium."""

    name = "playwright"
    supports_native_region = False

    def fetch(self, ctx: SourceContext, http: HttpClient) -> list[RawItem]:
        if not _PLAYWRIGHT_AVAILABLE:
            logger.warning(
                "playwright is not installed; skipping source=%r (pip install playwright && playwright install chromium)",
                ctx.source_label,
            )
            return []

        url, item_sel, title_sel, link_sel, date_sel = _parse_params(ctx)
        label = ctx.source_label
        timeout_ms = _timeout_ms(http)

        try:
            html = asyncio.run(
                _load_page_html(
                    url,
                    item_selector=item_sel,
                    timeout_ms=timeout_ms,
                    user_agent=USER_AGENT,
                )
            )
        except PlaywrightError as e:
            raise AdapterError(f"{label}: Playwright error fetching {url!r}: {e}") from e
        except Exception as e:
            raise AdapterError(f"{label}: failed to load page {url!r}: {e}") from e

        try:
            soup = BeautifulSoup(html, "html.parser")
            items = _extract_items(
                soup,
                item_sel=item_sel,
                title_sel=title_sel,
                link_sel=link_sel,
                date_sel=date_sel,
                source_label=label,
            )
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"{label}: unexpected error while extracting listings: {e}") from e

        logger.info(
            "playwright source=%r url=%r items=%d",
            label,
            url,
            len(items),
        )
        return items
