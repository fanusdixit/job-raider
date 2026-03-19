"""Atomic results.json write (Epic 3 Story 3.5)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from job_raider.merge import merge_run
from job_raider.models import AppConfig, Opportunity, SearchConfig
from job_raider.storage import write_results_atomic

RUN = datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc)


def test_atomic_write_and_read_json(tmp_path):
    cfg = AppConfig(
        searches=(SearchConfig(id="a", name="A", keywords=("k",), sources=()),),
    )
    doc = merge_run(
        previous_path=None,
        incoming=[
            Opportunity(
                dedupe_id="https://x.com/1",
                title="Job",
                source="Feed",
                url="https://x.com/1",
                search_id="a",
                search_name="A",
                published_at=None,
                last_seen_at=None,
            )
        ],
        app_config=cfg,
        run_at=RUN,
        tool_version="0.1.0",
    )
    path = tmp_path / "results.json"
    write_results_atomic(path, doc)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["tool_version"] == "0.1.0"
    assert data["generated_at"].endswith("Z")
    assert len(data["searches"]) == 1
    assert data["searches"][0]["items"][0]["dedupe_id"] == "https://x.com/1"
    assert data["source_runs"] == []


def test_write_creates_parent_dir(tmp_path):
    cfg = AppConfig(
        searches=(SearchConfig(id="a", name="A", keywords=("k",), sources=()),),
    )
    doc = merge_run(previous_path=None, incoming=[], app_config=cfg, run_at=RUN)
    nested = tmp_path / "out" / "dir" / "results.json"
    write_results_atomic(nested, doc)
    assert nested.is_file()
