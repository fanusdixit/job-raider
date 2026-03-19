"""RawItem → Opportunity + dedupe_id (Epic 2 Story 2.5)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from job_raider.exceptions import NormalizeError
from job_raider.matching import build_source_context
from job_raider.models import RawItem, SearchConfig, SourceConfig
from job_raider.normalize import normalize_and_filter, raw_to_opportunity, resolve_to_absolute_url
from job_raider.sources.base import SourceContext


def test_resolve_absolute_unchanged():
    assert resolve_to_absolute_url(
        "HTTPS://Ex.ORG/path#frag",
        None,
    ) == "HTTPS://Ex.ORG/path#frag"


def test_resolve_relative_with_base():
    u = resolve_to_absolute_url("/jobs/3", "https://careers.example.com")
    assert u == "https://careers.example.com/jobs/3"


def test_resolve_relative_without_base_raises():
    with pytest.raises(NormalizeError):
        resolve_to_absolute_url("/only/relative", None)


def test_raw_to_opportunity():
    raw = RawItem(
        title="T",
        url="https://EXAMPLE.COM/a?x=1#y",
        published_at=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
    )
    ctx = SourceContext(
        search_id="s",
        search_name="SN",
        expanded_keywords=(),
        region=None,
        source_label="Feed",
        params={"url": "https://ignore"},
    )
    opp = raw_to_opportunity(raw, ctx)
    assert opp.title == "T"
    assert opp.source == "Feed"
    assert opp.search_id == "s"
    assert opp.search_name == "SN"
    assert opp.published_at == raw.published_at
    assert opp.dedupe_id == "https://example.com/a?x=1"
    assert opp.url == "https://example.com/a?x=1"


def test_raw_to_opportunity_uses_link_base_from_ctx():
    raw = RawItem(title="R", url="/p/1")
    ctx = SourceContext(
        search_id="s",
        search_name="SN",
        expanded_keywords=(),
        region=None,
        source_label="X",
        params={"url": "https://x", "link_base": "https://site.example"},
    )
    opp = raw_to_opportunity(raw, ctx)
    assert opp.url == "https://site.example/p/1"


def test_normalize_and_filter_max_age_keeps_recent_and_null_published():
    rome = ZoneInfo("Europe/Rome")
    now = dt.datetime(2024, 6, 20, 12, 0, 0, tzinfo=rome)
    search = SearchConfig(
        id="s",
        name="S",
        keywords=("job",),
        region=None,
        sources=(),
        max_age_days=10,
    )
    source = SourceConfig("rss", "L", {"url": "https://x/f.xml"})

    class _Fake:
        name = "rss"
        supports_native_region = False

    ctx = build_source_context(search, source, _Fake())
    raws = [
        RawItem(
            title="job stale",
            url="https://x/1",
            published_at=dt.datetime(2024, 6, 1, 12, 0, 0, tzinfo=rome),
        ),
        RawItem(
            title="job fresh",
            url="https://x/2",
            published_at=dt.datetime(2024, 6, 15, 12, 0, 0, tzinfo=rome),
        ),
        RawItem(title="job undated", url="https://x/3", published_at=None),
    ]
    opps = normalize_and_filter(raws, ctx, keywords=ctx.expanded_keywords, now_rome=now)
    assert {o.title for o in opps} == {"job fresh", "job undated"}


def test_normalize_and_filter_now_rome_type_error():
    search = SearchConfig(
        id="s",
        name="S",
        keywords=("k",),
        region=None,
        sources=(),
        max_age_days=1,
    )
    source = SourceConfig("rss", "L", {"url": "https://x"})

    class _Fake:
        name = "rss"
        supports_native_region = False

    ctx = build_source_context(search, source, _Fake())
    with pytest.raises(TypeError, match="now_rome"):
        normalize_and_filter(
            [RawItem(title="k item", url="https://x/1", published_at=None)],
            ctx,
            keywords=ctx.expanded_keywords,
            now_rome="not-a-datetime",  # type: ignore[arg-type]
        )
