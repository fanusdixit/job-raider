"""
HTML listing adapter: BeautifulSoup + CSS selectors from YAML (architecture §5–6, Epic 4).
"""

from __future__ import annotations

import datetime as dt
import email.utils
import logging
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, Tag
from soupsieve.util import SelectorSyntaxError

from job_raider.exceptions import AdapterError
from job_raider.models import RawItem
from job_raider.sources.base import SourceContext

if TYPE_CHECKING:
    from job_raider.http_client import HttpClient

logger = logging.getLogger(__name__)


def _require_param(params: dict, key: str, label: str) -> str:
    raw = params.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise AdapterError(f"{label}: html_selectors param {key!r} must be a non-empty string")
    return raw.strip()


def _parse_published_at_from_element(el: Tag | None) -> dt.datetime | None:
    """Best-effort date from a selected element (time[datetime], data-date, text)."""
    if el is None:
        return None

    candidates: list[str] = []
    if el.name == "time":
        dt_attr = el.get("datetime")
        if isinstance(dt_attr, str) and dt_attr.strip():
            candidates.append(dt_attr.strip())
    for attr in ("data-date", "data-published", "datetime"):
        v = el.get(attr)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())

    text = el.get_text(strip=True)
    if text:
        candidates.append(text)

    for s in candidates:
        parsed = _parse_date_string(s)
        if parsed is not None:
            return parsed
    return None


def _parse_date_string(s: str) -> dt.datetime | None:
    s = s.strip()
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except ValueError:
        pass
    try:
        d = email.utils.parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _href_from_link_element(el: Tag | None) -> str | None:
    if el is None:
        return None
    if el.name == "a":
        href = el.get("href")
        return str(href).strip() if href else None
    inner = el.select_one("a[href]")
    if inner is not None:
        href = inner.get("href")
        return str(href).strip() if href else None
    return None


def _title_from_element(el: Tag | None) -> str:
    if el is None:
        return ""
    return el.get_text(separator=" ", strip=True)


def _extract_items(
    soup: BeautifulSoup,
    *,
    item_sel: str,
    title_sel: str,
    link_sel: str,
    date_sel: str | None,
    source_label: str,
) -> list[RawItem]:
    items: list[RawItem] = []
    try:
        nodes = soup.select(item_sel)
    except (ValueError, SelectorSyntaxError) as e:
        raise AdapterError(f"{source_label}: invalid CSS selector for item: {e}") from e

    for node in nodes:
        if not isinstance(node, Tag):
            continue
        try:
            title_el = node.select_one(title_sel)
            link_el = node.select_one(link_sel)
        except (ValueError, SelectorSyntaxError) as e:
            raise AdapterError(f"{source_label}: invalid title/link CSS selector: {e}") from e

        href = _href_from_link_element(link_el if link_el is not None else title_el)
        if not href:
            continue

        title = _title_from_element(title_el if title_el is not None else link_el)
        if not title:
            title = "(no title)"

        date_el = None
        if date_sel:
            try:
                date_el = node.select_one(date_sel)
            except (ValueError, SelectorSyntaxError) as e:
                raise AdapterError(f"{source_label}: invalid date CSS selector: {e}") from e

        published = _parse_published_at_from_element(date_el)

        items.append(
            RawItem(
                title=title,
                url=href,
                summary=None,
                published_at=published,
            )
        )

    return items


class HtmlSelectorsAdapter:
    name = "html_selectors"
    supports_native_region = False

    def fetch(self, ctx: SourceContext, http: HttpClient) -> list[RawItem]:
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

        try:
            response = http.get(url)
        except Exception as e:
            raise AdapterError(f"{label}: HTTP error fetching {url!r}: {e}") from e

        try:
            soup = BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            raise AdapterError(f"{label}: failed to parse HTML: {e}") from e

        try:
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
            "html_selectors source=%r url=%r items=%d",
            label,
            url,
            len(items),
        )
        return items
