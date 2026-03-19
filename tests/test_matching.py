"""OR keywords and region expansion (Epic 2 Story 2.4)."""

from __future__ import annotations

from job_raider.matching import (
    build_source_context,
    expand_keywords_for_filter,
    matches_raw_item,
)
from job_raider.models import RawItem, SearchConfig, SourceConfig


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
