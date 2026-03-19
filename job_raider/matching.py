"""
OR keyword matching, optional max age filter, and region-as-keyword expansion.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from job_raider.models import RawItem, SearchConfig, SourceConfig

ROME = ZoneInfo("Europe/Rome")
from job_raider.sources.base import SourceAdapter, SourceContext


def expand_keywords_for_filter(
    base_keywords: tuple[str, ...],
    region: str | None,
    *,
    supports_native_region: bool,
) -> tuple[str, ...]:
    """
    Effective keywords for substring OR matching.

    When the adapter does not support native region filtering, append ``region``
    as an extra token so it participates in OR matching (architecture §6).
    """
    if supports_native_region or not region or not str(region).strip():
        return base_keywords
    r = str(region).strip()
    r_cf = r.casefold()
    if any(k.casefold() == r_cf for k in base_keywords):
        return base_keywords
    return (*base_keywords, r)


def matches_raw_item(item: RawItem, keywords: tuple[str, ...]) -> bool:
    """
    True if **any** keyword matches as case-insensitive substring in title or summary.
    """
    if not keywords:
        return True
    title_cf = item.title.casefold()
    summary_cf = item.summary.casefold() if item.summary else ""
    for kw in keywords:
        kcf = kw.casefold()
        if kcf in title_cf:
            return True
        if summary_cf and kcf in summary_cf:
            return True
    return False


def raw_passes_max_age(
    item: RawItem,
    *,
    max_age_days: int | None,
    now_rome: datetime,
) -> bool:
    """
    When ``max_age_days`` is set, drop items whose ``published_at`` is strictly older
    than that many days compared to ``now_rome`` (both interpreted in Europe/Rome).

    Items with ``published_at`` None always pass. When ``max_age_days`` is None, passes.
    """
    if max_age_days is None:
        return True
    if item.published_at is None:
        return True
    now_r = now_rome.astimezone(ROME)
    pub = item.published_at
    if pub.tzinfo is None:
        pub_r = pub.replace(tzinfo=ROME)
    else:
        pub_r = pub.astimezone(ROME)
    age = now_r - pub_r
    return age <= timedelta(days=max_age_days)


def build_source_context(
    search: SearchConfig,
    source: SourceConfig,
    adapter: SourceAdapter,
) -> SourceContext:
    """Build fetch context with expanded keywords for this adapter."""
    expanded = expand_keywords_for_filter(
        search.keywords,
        search.region,
        supports_native_region=adapter.supports_native_region,
    )
    return SourceContext(
        search_id=search.id,
        search_name=search.name,
        expanded_keywords=expanded,
        region=search.region,
        source_label=source.label,
        params=dict(source.params),
        max_age_days=search.max_age_days,
    )
