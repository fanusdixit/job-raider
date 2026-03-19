"""RawItem → Opportunity + dedupe_id (Epic 2 Story 2.5)."""

from __future__ import annotations

import datetime as dt

import pytest

from job_raider.exceptions import NormalizeError
from job_raider.models import RawItem
from job_raider.normalize import raw_to_opportunity, resolve_to_absolute_url
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
