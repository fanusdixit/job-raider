"""OR keywords, max age, and region expansion (Epic 2 Story 2.4)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from job_raider.matching import (
    build_source_context,
    expand_keywords_for_filter,
    matches_raw_item,
    raw_matches_any_exclude_keyword,
    raw_passes_max_age,
    raw_passes_require_keywords,
)
from job_raider.models import RawItem, SearchConfig, SourceConfig

ROME = ZoneInfo("Europe/Rome")


def test_or_keyword_title():
    raw = RawItem(title="Senior Python Developer", url="https://x/a")
    assert matches_raw_item(raw, ("java", "python")) is True
    assert matches_raw_item(raw, ("java", "rust")) is False


def test_or_keyword_summary():
    raw = RawItem(
        title="Role",
        url="https://x/a",
        summary="Must know Django framework",
    )
    assert matches_raw_item(raw, ("django",)) is True
    assert matches_raw_item(raw, ("flask",)) is False


def test_case_insensitive():
    raw = RawItem(title="PYTHON job", url="https://x/a")
    assert matches_raw_item(raw, ("python",)) is True


def test_empty_keywords_matches_all():
    raw = RawItem(title="Anything", url="https://x/a")
    assert matches_raw_item(raw, ()) is True


def test_region_appended_when_not_native():
    k = expand_keywords_for_filter(("a", "b"), "Lazio", supports_native_region=False)
    assert k == ("a", "b", "Lazio")


def test_region_not_duplicated_if_already_keyword():
    k = expand_keywords_for_filter(("a", "lazio"), "Lazio", supports_native_region=False)
    assert k == ("a", "lazio")


def test_region_skipped_when_native_supported():
    k = expand_keywords_for_filter(("a",), "Lazio", supports_native_region=True)
    assert k == ("a",)


def test_build_source_context():
    search = SearchConfig(
        id="s1",
        name="S",
        keywords=("kw",),
        region="Campania",
        sources=(),
    )
    source = SourceConfig(adapter="rss", label="L", params={"url": "https://x/f.xml"})

    class FakeAdapter:
        name = "rss"
        supports_native_region = False

    ctx = build_source_context(search, source, FakeAdapter())
    assert ctx.search_id == "s1"
    assert ctx.expanded_keywords == ("kw", "Campania")
    assert ctx.source_label == "L"
    assert ctx.max_age_days is None


def test_raw_passes_require_keywords_empty_tuple_always_true():
    raw = RawItem(title="Anything", url="https://x/a")
    assert raw_passes_require_keywords(raw, ()) is True


def test_raw_passes_require_keywords_or_in_title_or_summary():
    raw = RawItem(title="News", url="https://x/a", summary="Avviso pubblico")
    assert raw_passes_require_keywords(raw, ("bando",)) is False
    assert raw_passes_require_keywords(raw, ("avviso",)) is True


def test_raw_matches_exclude_keyword_in_title():
    raw = RawItem(title="Premiato lo studente", url="https://x/a")
    assert raw_matches_any_exclude_keyword(raw, ("premiato",)) is True
    assert raw_matches_any_exclude_keyword(raw, ("iscrizioni",)) is False


def test_raw_matches_exclude_empty_tuple_false():
    raw = RawItem(title="X", url="https://x/a")
    assert raw_matches_any_exclude_keyword(raw, ()) is False


def test_build_source_context_passes_require_and_exclude():
    search = SearchConfig(
        id="s1",
        name="S",
        keywords=("kw",),
        region=None,
        sources=(),
        require_keywords=("bando",),
        exclude_keywords=("iscrizioni",),
    )
    source = SourceConfig(adapter="rss", label="L", params={"url": "https://x/f.xml"})

    class FakeAdapter:
        name = "rss"
        supports_native_region = False

    ctx = build_source_context(search, source, FakeAdapter())
    assert ctx.require_keywords == ("bando",)
    assert ctx.exclude_keywords == ("iscrizioni",)


def test_build_source_context_passes_max_age_days():
    search = SearchConfig(
        id="s1",
        name="S",
        keywords=("kw",),
        region=None,
        sources=(),
        max_age_days=14,
    )
    source = SourceConfig(adapter="rss", label="L", params={"url": "https://x/f.xml"})

    class FakeAdapter:
        name = "rss"
        supports_native_region = False

    ctx = build_source_context(search, source, FakeAdapter())
    assert ctx.max_age_days == 14


def test_raw_passes_max_age_when_unset():
    raw = RawItem(
        title="T",
        url="https://x/a",
        published_at=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc),
    )
    assert raw_passes_max_age(raw, max_age_days=None, now_rome=dt.datetime.now(ROME)) is True


def test_raw_passes_max_age_null_published_always_passes():
    raw = RawItem(title="T", url="https://x/a", published_at=None)
    assert (
        raw_passes_max_age(
            raw,
            max_age_days=1,
            now_rome=dt.datetime(2024, 6, 15, tzinfo=ROME),
        )
        is True
    )


def test_raw_passes_max_age_within_window():
    now = dt.datetime(2024, 6, 15, 12, 0, 0, tzinfo=ROME)
    pub = dt.datetime(2024, 6, 12, 12, 0, 0, tzinfo=ROME)
    raw = RawItem(title="T", url="https://x/a", published_at=pub)
    assert raw_passes_max_age(raw, max_age_days=5, now_rome=now) is True


def test_raw_passes_max_age_outside_window():
    now = dt.datetime(2024, 6, 15, 12, 0, 0, tzinfo=ROME)
    pub = dt.datetime(2024, 6, 8, 12, 0, 0, tzinfo=ROME)
    raw = RawItem(title="T", url="https://x/a", published_at=pub)
    assert raw_passes_max_age(raw, max_age_days=5, now_rome=now) is False


def test_raw_passes_max_age_naive_published_interpreted_as_rome():
    now = dt.datetime(2024, 6, 15, 12, 0, 0, tzinfo=ROME)
    pub = dt.datetime(2024, 6, 14, 12, 0, 0)
    raw = RawItem(title="T", url="https://x/a", published_at=pub)
    assert raw_passes_max_age(raw, max_age_days=5, now_rome=now) is True
