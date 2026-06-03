"""
Runtime adapter instances (architecture §6, NFR6).
"""

from __future__ import annotations

from job_raider.sources.base import SourceAdapter
from job_raider.sources.html_selectors import HtmlSelectorsAdapter
from job_raider.sources.playwright_adapter import PlaywrightAdapter
from job_raider.sources.rss import RssAdapter

_ADAPTERS: dict[str, SourceAdapter] = {
    "rss": RssAdapter(),
    "html_selectors": HtmlSelectorsAdapter(),
    "playwright": PlaywrightAdapter(),
}


def get_adapter(name: str) -> SourceAdapter:
    """Return the adapter implementation for a validated config name."""
    return _ADAPTERS[name]
