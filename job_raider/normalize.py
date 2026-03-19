"""
RawItem → Opportunity with absolute URL and ``dedupe_id`` (architecture §6.3, §8.1).
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse, urljoin
from zoneinfo import ZoneInfo

from job_raider.dedupe import compute_dedupe_id
from job_raider.exceptions import NormalizeError
from job_raider.models import Opportunity, RawItem
from job_raider.sources.base import SourceContext


def resolve_to_absolute_url(url: str, link_base: str | None) -> str:
    """
    If ``url`` has no netloc, join with ``link_base`` (must be http(s) absolute).
    """
    u = url.strip()
    parsed = urlparse(u)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return u
    if not link_base or not str(link_base).strip():
        raise NormalizeError(
            f"Relative URL {url!r} requires a non-empty link_base in source params"
        )
    base = str(link_base).strip()
    joined = urljoin(base if base.endswith("/") else base + "/", u)
    parsed_j = urlparse(joined)
    if not parsed_j.scheme or not parsed_j.netloc:
        raise NormalizeError(f"Could not resolve URL {url!r} with link_base {base!r}")
    return joined


def raw_to_opportunity(
    raw: RawItem,
    ctx: SourceContext,
    *,
    link_base: str | None = None,
) -> Opportunity:
    """
    Normalize a raw row into an ``Opportunity`` with ``dedupe_id`` from normalized URL.

    ``link_base`` defaults from ``ctx.params.get("link_base")``.
    """
    base = link_base if link_base is not None else ctx.params.get("link_base")
    if base is not None and isinstance(base, str):
        base = base.strip() or None
    else:
        base = None

    abs_url = resolve_to_absolute_url(raw.url, base)
    try:
        dedupe_id = compute_dedupe_id(abs_url)
    except ValueError as e:
        raise NormalizeError(str(e)) from e

    # Canonical http(s) URL (lowercased host, no fragment) for storage and href
    canonical_url = dedupe_id

    return Opportunity(
        dedupe_id=dedupe_id,
        title=raw.title,
        source=ctx.source_label,
        url=canonical_url,
        search_id=ctx.search_id,
        search_name=ctx.search_name,
        published_at=raw.published_at,
        last_seen_at=None,
    )


def normalize_and_filter(
    raws: list[RawItem],
    ctx: SourceContext,
    *,
    keywords: tuple[str, ...],
    now_rome: datetime | None = None,
) -> list[Opportunity]:
    """
    Apply OR keyword filter, optional ``max_age_days`` (Europe/Rome via ``ctx``), then normalize.

    ``now_rome`` is the reference instant for age filtering (any tz-aware or naive datetime;
    naive values are treated as Europe/Rome). Defaults to ``datetime.now(Europe/Rome)``.

    Skips items that fail normalization (caller may log in pipeline E5).
    """
    from job_raider.matching import matches_raw_item, raw_passes_max_age

    rome = ZoneInfo("Europe/Rome")
    if now_rome is None:
        now = datetime.now(rome)
    else:
        if not isinstance(now_rome, datetime):
            raise TypeError("now_rome must be datetime or None")
        now = now_rome
        if now.tzinfo is None:
            now = now.replace(tzinfo=rome)

    out: list[Opportunity] = []
    for raw in raws:
        if not matches_raw_item(raw, keywords):
            continue
        if not raw_passes_max_age(raw, max_age_days=ctx.max_age_days, now_rome=now):
            continue
        try:
            out.append(raw_to_opportunity(raw, ctx))
        except NormalizeError:
            continue
    return out
