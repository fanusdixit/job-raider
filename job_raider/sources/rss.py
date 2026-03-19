"""
RSS / Atom feed adapter (feedparser + HttpClient).
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import TYPE_CHECKING

import feedparser

from job_raider.exceptions import AdapterError
from job_raider.models import RawItem
from job_raider.sources.base import SourceContext

if TYPE_CHECKING:
    from job_raider.http_client import HttpClient


def _published_to_datetime(entry: dict) -> dt.datetime | None:
    """Parse feedparser entry published/updated into timezone-aware UTC or None."""
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct is None:
            continue
        try:
            ts = calendar.timegm(struct)
            return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def _entry_link(entry: dict) -> str | None:
    link = entry.get("link")
    if link and str(link).strip():
        return str(link).strip()
    links = entry.get("links") or []
    for lnk in links:
        href = lnk.get("href") if isinstance(lnk, dict) else None
        if href and str(href).strip():
            return str(href).strip()
    return None


def _entry_title(entry: dict) -> str:
    t = entry.get("title")
    if t is None:
        return ""
    # feedparser may include HTML in title
    return str(t).strip()


def _entry_summary(entry: dict) -> str | None:
    for key in ("summary", "description", "subtitle"):
        val = entry.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return None


class RssAdapter:
    name = "rss"
    supports_native_region = False

    def fetch(self, ctx: SourceContext, http: HttpClient) -> list[RawItem]:
        url = ctx.params.get("url")
        if not url or not isinstance(url, str):
            raise AdapterError(f"{ctx.source_label}: rss source missing url in params")

        try:
            response = http.get(url)
        except Exception as e:
            raise AdapterError(f"{ctx.source_label}: HTTP error fetching {url!r}: {e}") from e

        try:
            parsed = feedparser.parse(response.content)
        except Exception as e:
            raise AdapterError(f"{ctx.source_label}: failed to parse feed: {e}") from e

        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
            exc = getattr(parsed, "bozo_exception", None)
            hint = f" ({exc})" if exc else ""
            raise AdapterError(f"{ctx.source_label}: malformed feed{hint}")

        items: list[RawItem] = []
        for entry in parsed.entries or []:
            if not isinstance(entry, dict):
                entry = dict(entry)
            link = _entry_link(entry)
            if not link:
                continue
            title = _entry_title(entry)
            if not title:
                title = "(no title)"
            summary = _entry_summary(entry)
            published = _published_to_datetime(entry)
            items.append(
                RawItem(
                    title=title,
                    url=link,
                    summary=summary,
                    published_at=published,
                )
            )
        return items
