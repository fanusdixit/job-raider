"""Merge, prune, sort, load (Epic 3)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from job_raider.exceptions import ResultsLoadError
from job_raider.merge import (
    RETENTION,
    _StoredEntry,
    apply_incoming,
    build_results_document,
    load_results_state,
    merge_run,
    prune_stale,
    sort_items_for_search,
)
from job_raider.models import AppConfig, Opportunity, SearchConfig
from job_raider.storage import write_results_atomic


def _cfg(*searches: SearchConfig) -> AppConfig:
    return AppConfig(searches=searches)


def _opp(
    *,
    did: str,
    sid: str,
    sname: str,
    title: str = "T",
    pub: datetime | None = None,
) -> Opportunity:
    return Opportunity(
        dedupe_id=did,
        title=title,
        source="S",
        url=did,
        search_id=sid,
        search_name=sname,
        published_at=pub,
        last_seen_at=None,
    )


RUN0 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_load_missing_file(tmp_path):
    assert load_results_state(tmp_path / "nope.json") == {}


def test_load_malformed_json(tmp_path):
    p = tmp_path / "r.json"
    p.write_text("{broken", encoding="utf-8")
    with pytest.raises(ResultsLoadError, match="invalid JSON"):
        load_results_state(p)


def test_load_unsupported_schema_version(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(
        json.dumps({"schema_version": 99, "searches": []}),
        encoding="utf-8",
    )
    with pytest.raises(ResultsLoadError, match="unsupported schema_version"):
        load_results_state(p)


def test_load_roundtrip_minimal(tmp_path):
    cfg = _cfg(SearchConfig(id="s1", name="One", keywords=("k",), sources=()))
    doc = merge_run(
        previous_path=None,
        incoming=[_opp(did="https://x.com/1", sid="s1", sname="One")],
        app_config=cfg,
        run_at=RUN0,
        tool_version="0.1.0",
    )
    p = tmp_path / "out.json"
    write_results_atomic(p, doc)
    state = load_results_state(p)
    assert "s1" in state
    assert "https://x.com/1" in state["s1"]


def test_merge_seen_sets_last_seen():
    state: dict = {}
    run1 = RUN0
    run2 = RUN0 + timedelta(days=1)
    apply_incoming(
        state,
        [_opp(did="https://a/1", sid="s", sname="S")],
        run_at=run1,
    )
    assert state["s"]["https://a/1"].last_seen_at == run1
    apply_incoming(
        state,
        [_opp(did="https://a/1", sid="s", sname="S")],
        run_at=run2,
    )
    assert state["s"]["https://a/1"].last_seen_at == run2


def test_merge_not_seen_preserves_last_seen():
    state: dict = {}
    run1 = RUN0
    run2 = RUN0 + timedelta(days=1)
    apply_incoming(state, [_opp(did="https://a/1", sid="s", sname="S")], run_at=run1)
    apply_incoming(state, [], run_at=run2)
    assert state["s"]["https://a/1"].last_seen_at == run1


def test_merge_updates_title():
    state: dict = {}
    apply_incoming(
        state,
        [_opp(did="https://a/1", sid="s", sname="S", title="Old")],
        run_at=RUN0,
    )
    apply_incoming(
        state,
        [_opp(did="https://a/1", sid="s", sname="S", title="New")],
        run_at=RUN0 + timedelta(hours=1),
    )
    assert state["s"]["https://a/1"].title == "New"


def test_prune_drops_older_than_30_days():
    run_at = RUN0
    last = run_at - RETENTION - timedelta(seconds=1)
    state = {
        "s": {
            "https://a/1": _StoredEntry(
                dedupe_id="https://a/1",
                title="T",
                source="S",
                url="https://a/1",
                published_at=None,
                last_seen_at=last,
                search_id="s",
                search_name="S",
            )
        }
    }
    prune_stale(state, run_at=run_at)
    assert "s" not in state


def test_prune_keeps_exactly_30_days_boundary():
    state: dict = {}
    run_at = RUN0
    last = run_at - RETENTION
    apply_incoming(state, [_opp(did="https://a/1", sid="s", sname="S")], run_at=last)
    apply_incoming(state, [], run_at=run_at)
    prune_stale(state, run_at=run_at)
    assert "https://a/1" in state["s"]


def test_sort_dated_desc_null_last():
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2024, 6, 1, tzinfo=timezone.utc)
    items = [
        _StoredEntry("u1", "B", "S", "u1", t0, RUN0, "s", "S"),
        _StoredEntry("u2", "A", "S", "u2", t1, RUN0, "s", "S"),
        _StoredEntry("u3", "Z", "S", "u3", None, RUN0, "s", "S"),
        _StoredEntry("u4", "M", "S", "u4", None, RUN0, "s", "S"),
    ]
    out = sort_items_for_search(list(items))
    assert [x.dedupe_id for x in out[:2]] == ["u2", "u1"]
    assert {x.dedupe_id for x in out[2:]} == {"u3", "u4"}
    assert out[2].title == "M" and out[3].title == "Z"


def test_sort_dated_tiebreak_title():
    t = datetime(2024, 1, 1, tzinfo=timezone.utc)
    items = [
        _StoredEntry("u1", "beta", "S", "u1", t, RUN0, "s", "S"),
        _StoredEntry("u2", "Alpha", "S", "u2", t, RUN0, "s", "S"),
    ]
    out = sort_items_for_search(items)
    # Same published_at: tie-break title casefold ascending (architecture §9)
    assert out[0].title == "Alpha"
    assert out[1].title == "beta"


def test_search_blocks_ordered_by_id():
    cfg = _cfg(
        SearchConfig(id="z", name="Z", keywords=("k",), sources=()),
        SearchConfig(id="a", name="A", keywords=("k",), sources=()),
    )
    state: dict = {}
    apply_incoming(state, [_opp(did="https://z/1", sid="z", sname="Z")], run_at=RUN0)
    apply_incoming(state, [_opp(did="https://a/1", sid="a", sname="A")], run_at=RUN0)
    doc = build_results_document(state, app_config=cfg, run_at=RUN0)
    assert [b.id for b in doc.searches] == ["a", "z"]


def test_empty_search_section_in_output():
    cfg = _cfg(
        SearchConfig(id="a", name="A", keywords=("k",), sources=()),
        SearchConfig(id="b", name="B", keywords=("k",), sources=()),
    )
    state: dict = {}
    apply_incoming(state, [_opp(did="https://x/1", sid="a", sname="A")], run_at=RUN0)
    doc = build_results_document(state, app_config=cfg, run_at=RUN0)
    assert len(doc.searches) == 2
    assert doc.searches[0].id == "a" and len(doc.searches[0].items) == 1
    assert doc.searches[1].id == "b" and doc.searches[1].items == []


def test_orphan_search_dropped_from_output(tmp_path):
    """Stored search id not in config is omitted from written document."""
    cfg = _cfg(SearchConfig(id="keep", name="K", keywords=("k",), sources=()))
    raw = {
        "schema_version": 1,
        "generated_at": "2020-01-01T00:00:00Z",
        "tool_version": "x",
        "searches": [
            {
                "id": "orphan",
                "name": "O",
                "items": [
                    {
                        "dedupe_id": "https://o/1",
                        "title": "t",
                        "source": "s",
                        "url": "https://o/1",
                        "published_at": None,
                        "last_seen_at": "2020-01-01T00:00:00Z",
                        "search_id": "orphan",
                        "search_name": "O",
                    }
                ],
            }
        ],
    }
    p = tmp_path / "in.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    doc = merge_run(previous_path=p, incoming=[], app_config=cfg, run_at=RUN0)
    assert len(doc.searches) == 1
    assert doc.searches[0].id == "keep"
    assert doc.searches[0].items == []


def test_item_missing_last_seen_raises(tmp_path):
    p = tmp_path / "x.json"
    bad = {
        "schema_version": 1,
        "searches": [
            {
                "id": "s",
                "name": "S",
                "items": [
                    {
                        "dedupe_id": "https://a",
                        "title": "t",
                        "source": "s",
                        "url": "https://a",
                        "published_at": None,
                        "search_id": "s",
                        "search_name": "S",
                    }
                ],
            }
        ],
    }
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ResultsLoadError, match="last_seen_at"):
        load_results_state(p)


def test_merge_run_full(tmp_path):
    cfg = _cfg(SearchConfig(id="s1", name="One", keywords=("k",), sources=()))
    doc = merge_run(
        previous_path=None,
        incoming=[
            _opp(
                did="https://jobs.example/p/1",
                sid="s1",
                sname="One",
                title="Role",
                pub=datetime(2025, 1, 2, tzinfo=timezone.utc),
            )
        ],
        app_config=cfg,
        run_at=RUN0,
    )
    assert doc.schema_version == 1
    assert doc.generated_at.endswith("Z")
    assert doc.tool_version
    assert len(doc.searches[0].items) == 1
    it = doc.searches[0].items[0]
    assert it.last_seen_at.endswith("Z")


def test_merge_run_file_preserves_last_seen_when_not_seen_second_run(tmp_path):
    """Epic 7: second run with empty incoming does not bump last_seen_at."""
    cfg = _cfg(SearchConfig(id="s1", name="One", keywords=("python",), sources=()))
    p = tmp_path / "state.json"
    t1 = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 10, 18, 0, 0, tzinfo=timezone.utc)
    o = _opp(did="https://x.com/1", sid="s1", sname="One", title="Python role")
    doc1 = merge_run(previous_path=None, incoming=[o], app_config=cfg, run_at=t1)
    write_results_atomic(p, doc1)
    doc2 = merge_run(previous_path=p, incoming=[], app_config=cfg, run_at=t2)
    write_results_atomic(p, doc2)
    data = json.loads(p.read_text(encoding="utf-8"))
    item = data["searches"][0]["items"][0]
    assert item["last_seen_at"] == "2026-01-10T12:00:00Z"


def test_merge_run_file_refreshes_last_seen_when_seen_again(tmp_path):
    """Epic 7: item present again on a later run updates last_seen_at."""
    cfg = _cfg(SearchConfig(id="s1", name="One", keywords=("python",), sources=()))
    p = tmp_path / "state.json"
    t1 = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
    o = _opp(did="https://x.com/1", sid="s1", sname="One", title="Python role")
    write_results_atomic(p, merge_run(previous_path=None, incoming=[o], app_config=cfg, run_at=t1))
    write_results_atomic(p, merge_run(previous_path=p, incoming=[o], app_config=cfg, run_at=t2))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["searches"][0]["items"][0]["last_seen_at"] == "2026-01-11T12:00:00Z"
