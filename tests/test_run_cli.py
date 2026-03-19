"""run.py CLI (Epic 5 Story 5.3)."""

from __future__ import annotations

import textwrap
from pathlib import Path


def test_run_main_invalid_config_exit_code(tmp_path):
    import run as run_mod

    p = tmp_path / "x.yaml"
    p.write_text("searches: []\n", encoding="utf-8")
    assert run_mod.main([str(p), "--results", str(tmp_path / "r.json"), "--index", str(tmp_path / "i.html")]) == 1


def test_run_main_success_with_stubbed_pipeline(tmp_path, monkeypatch):
    import run as run_mod

    cfg = tmp_path / "ok.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            searches:
              - id: a
                name: A
                keywords: [k]
                sources:
                  - adapter: rss
                    label: L
                    url: https://x/f
            """
        ).strip(),
        encoding="utf-8",
    )

    def fake_run(**kwargs):
        (tmp_path / "r.json").write_text("{}", encoding="utf-8")
        (tmp_path / "i.html").write_text("<html></html>", encoding="utf-8")
        return 0

    monkeypatch.setattr("job_raider.pipeline.run", fake_run)
    rc = run_mod.main(
        [str(cfg), "--results", str(tmp_path / "r.json"), "--index", str(tmp_path / "i.html")]
    )
    assert rc == 0
