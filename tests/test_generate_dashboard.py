"""Static index.html generation (Epic 5 Story 5.1)."""

from __future__ import annotations

from job_raider.generate_dashboard import (
    build_index_html,
    format_date_display,
    is_new_badge,
    safe_href,
)
from job_raider.models import OpportunityRecord, ResultsDocument, SearchResults, SourceRunRecord


def _doc(
    *,
    generated_at: str,
    items: list[OpportunityRecord],
    source_runs: tuple[SourceRunRecord, ...] = (),
) -> ResultsDocument:
    return ResultsDocument(
        schema_version=1,
        generated_at=generated_at,
        tool_version="0.1.0",
        searches=[SearchResults(id="s1", name="Section & Co", items=items)],
        source_runs=source_runs,
    )


def test_safe_href_only_http():
    assert safe_href("https://a.example/x") is not None
    assert safe_href("javascript:alert(1)") is None
    assert safe_href("/relative") is None


def test_escape_title_and_no_script_injection():
    it = OpportunityRecord(
        dedupe_id="https://x/1",
        title='Evil <script>alert(1)</script>',
        source='Src "',
        url="https://x/1",
        published_at=None,
        last_seen_at="2026-01-01T00:00:00Z",
        search_id="s1",
        search_name="S",
    )
    html_out = build_index_html(_doc(generated_at="2026-01-01T12:00:00Z", items=[it]))
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_new_badge_within_48h():
    it = OpportunityRecord(
        dedupe_id="https://x/1",
        title="Fresh",
        source="So",
        url="https://x/1",
        published_at="2026-03-18T14:00:00Z",
        last_seen_at="2026-03-19T14:00:00Z",
        search_id="s1",
        search_name="S",
    )
    assert is_new_badge(it.published_at, "2026-03-19T14:00:00Z") is True
    html_out = build_index_html(_doc(generated_at="2026-03-19T14:00:00Z", items=[it]))
    assert 'class="badge badge--new"' in html_out


def test_no_new_badge_when_published_at_null():
    it = OpportunityRecord(
        dedupe_id="https://x/1",
        title="N",
        source="So",
        url="https://x/1",
        published_at=None,
        last_seen_at="2026-03-19T14:00:00Z",
        search_id="s1",
        search_name="S",
    )
    assert is_new_badge(None, "2026-03-19T14:00:00Z") is False
    html_out = build_index_html(_doc(generated_at="2026-03-19T14:00:00Z", items=[it]))
    assert 'class="badge badge--new"' not in html_out


def test_format_date_display_em_dash_for_null():
    assert format_date_display(None) == "—"


def test_empty_section_renders_placeholder():
    doc = _doc(generated_at="2026-01-01T00:00:00Z", items=[])
    html_out = build_index_html(doc)
    assert "Nessun risultato" in html_out


def test_dashboard_list_order_matches_sorted_items_null_dates_last():
    """Epic 7: renderer preserves merge sort — dated desc, then nulls by title."""
    items = [
        OpportunityRecord(
            dedupe_id="https://x/new",
            title="Dated newer",
            source="S",
            url="https://x/new",
            published_at="2025-06-01T00:00:00Z",
            last_seen_at="2026-01-01T00:00:00Z",
            search_id="s1",
            search_name="S",
        ),
        OpportunityRecord(
            dedupe_id="https://x/old",
            title="Dated older",
            source="S",
            url="https://x/old",
            published_at="2025-01-01T00:00:00Z",
            last_seen_at="2026-01-01T00:00:00Z",
            search_id="s1",
            search_name="S",
        ),
        OpportunityRecord(
            dedupe_id="https://x/na",
            title="Null apple",
            source="S",
            url="https://x/na",
            published_at=None,
            last_seen_at="2026-01-01T00:00:00Z",
            search_id="s1",
            search_name="S",
        ),
        OpportunityRecord(
            dedupe_id="https://x/nz",
            title="Null zebra",
            source="S",
            url="https://x/nz",
            published_at=None,
            last_seen_at="2026-01-01T00:00:00Z",
            search_id="s1",
            search_name="S",
        ),
    ]
    html_out = build_index_html(_doc(generated_at="2026-01-01T12:00:00Z", items=items))
    i_newer = html_out.index("Dated newer")
    i_older = html_out.index("Dated older")
    i_apple = html_out.index("Null apple")
    i_zebra = html_out.index("Null zebra")
    assert i_newer < i_older < i_apple < i_zebra


def test_new_badge_false_when_published_older_than_48h_window():
    """Epic 7: outside 48h in Europe/Rome comparison → no badge."""
    assert (
        is_new_badge("2026-03-17T12:00:00Z", "2026-03-19T14:00:00Z") is False
    )


def test_new_badge_true_at_exactly_48h_boundary():
    assert is_new_badge("2026-03-17T14:00:00Z", "2026-03-19T14:00:00Z") is True


def test_new_badge_naive_published_interpreted_as_europe_rome():
    """Naive published_at is treated as Europe/Rome (architecture §9)."""
    # Mid-winter avoids EU DST edge cases for stable Rome offsets.
    assert is_new_badge("2026-01-15T15:00:00", "2026-01-16T14:00:00Z") is True


def test_run_report_is_collapsible_details_closed_by_default():
    doc = _doc(
        generated_at="2026-01-15T12:00:00Z",
        items=[],
        source_runs=(
            SourceRunRecord(
                search_id="s1",
                search_name="Section & Co",
                source_label="Feed A",
                status="ok",
                item_count=0,
            ),
        ),
    )
    html_out = build_index_html(doc)
    assert '<details class="run-report">' in html_out
    assert "<summary>Report ultima esecuzione</summary>" in html_out
    assert " open" not in html_out.split("<details", 1)[1].split(">", 1)[0]


def test_run_report_shows_category_totals_and_source_table():
    it = OpportunityRecord(
        dedupe_id="https://x/1",
        title="T",
        source="Feed A",
        url="https://x/1",
        published_at=None,
        last_seen_at="2026-01-01T00:00:00Z",
        search_id="s1",
        search_name="Section & Co",
    )
    doc = _doc(
        generated_at="2026-01-15T12:00:00Z",
        items=[it],
        source_runs=(
            SourceRunRecord(
                search_id="s1",
                search_name="Section & Co",
                source_label="Feed A",
                status="ok",
                item_count=3,
            ),
            SourceRunRecord(
                search_id="s1",
                search_name="Section & Co",
                source_label="Feed B",
                status="error",
                item_count=0,
                error_detail='broken <feed>',
            ),
        ),
    )
    html_out = build_index_html(doc)
    assert "Totale risultati per categoria" in html_out
    assert "<strong>Section &amp; Co</strong>: 1</li>" in html_out
    assert "Feed A" in html_out
    assert "Feed B" in html_out
    assert "run-report__status-ok" in html_out
    assert "run-report__status-err" in html_out
    assert "&lt;feed&gt;" in html_out
    assert "<feed>" not in html_out


def test_run_report_without_source_runs_shows_placeholder():
    doc = _doc(generated_at="2026-01-15T12:00:00Z", items=[])
    html_out = build_index_html(doc)
    assert "Dettaglio per fonte non disponibile" in html_out


def test_no_new_badge_outside_window_in_rendered_html():
    it = OpportunityRecord(
        dedupe_id="https://x/1",
        title="Stale listing",
        source="So",
        url="https://x/1",
        published_at="2026-03-10T10:00:00Z",
        last_seen_at="2026-03-19T14:00:00Z",
        search_id="s1",
        search_name="S",
    )
    html_out = build_index_html(_doc(generated_at="2026-03-19T14:00:00Z", items=[it]))
    assert 'class="badge badge--new"' not in html_out
