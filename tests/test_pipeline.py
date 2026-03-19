"""Pipeline orchestration (Epic 5)."""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from pathlib import Path

from job_raider.models import Opportunity, SourceRunRecord
from job_raider import pipeline as pipeline_mod


def test_pipeline_writes_json_and_html(tmp_path, monkeypatch):
    cfg_file = tmp_path / "searches.yaml"
    cfg_file.write_text(
        textwrap.dedent(
            """
            searches:
              - id: t
                name: T
                keywords: [k]
                sources:
                  - adapter: rss
                    label: L
                    url: https://example.com/f.xml
            """
        ).strip(),
        encoding="utf-8",
    )
    results = tmp_path / "results.json"
    index = tmp_path / "index.html"

    def fake_collect(cfg, http, robots=None):  # noqa: ARG001
        opps = [
            Opportunity(
                dedupe_id="https://jobs.example/p/1",
                title="Role",
                source="L",
                url="https://jobs.example/p/1",
                search_id="t",
                search_name="T",
                published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                last_seen_at=None,
            )
        ]
        runs = (
            SourceRunRecord(
                search_id="t",
                search_name="T",
                source_label="L",
                status="ok",
                item_count=1,
            ),
        )
        return opps, 0, runs

    monkeypatch.setattr(pipeline_mod, "collect_opportunities", fake_collect)

    code = pipeline_mod.run(
        config_path=cfg_file,
        results_path=results,
        index_path=index,
    )
    assert code == 0
    assert results.is_file()
    assert index.is_file()
    text = index.read_text(encoding="utf-8")
    assert "Role" in text
    assert "https://jobs.example/p/1" in text


def test_pipeline_config_error_returns_1(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("searches: []\n", encoding="utf-8")
    code = pipeline_mod.run(
        config_path=bad,
        results_path=tmp_path / "r.json",
        index_path=tmp_path / "i.html",
    )
    assert code == 1


def test_run_with_paths_string(tmp_path, monkeypatch):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(
        textwrap.dedent(
            """
            searches:
              - id: a
                name: A
                keywords: [x]
                sources:
                  - adapter: rss
                    label: R
                    url: https://x/f
            """
        ).strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        pipeline_mod,
        "collect_opportunities",
        lambda *a, **k: ([], 0, ()),
    )

    assert (
        pipeline_mod.run_with_paths(
            cfg_file,
            str(tmp_path / "out.json"),
            str(tmp_path / "out.html"),
        )
        == 0
    )
