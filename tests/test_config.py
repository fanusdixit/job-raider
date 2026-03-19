"""Fail-fast config tests — no HTTP (Epic 1 Story 1.4)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from job_raider.config import load_searches, parse_searches_yaml
from job_raider.exceptions import ConfigError


def _valid_minimal_yaml() -> str:
    return textwrap.dedent(
        """
        version: 1
        searches:
          - id: s1
            name: "Search one"
            keywords: [a, b]
            sources:
              - adapter: rss
                label: "L1"
                url: "https://example.com/feed.xml"
        """
    ).strip()


def test_parse_valid_without_version_key():
    raw = textwrap.dedent(
        """
        searches:
          - id: s1
            name: "Search one"
            keywords: [a]
            sources:
              - adapter: rss
                label: "L1"
                url: "https://example.com/feed.xml"
        """
    ).strip()
    cfg = parse_searches_yaml(raw)
    assert cfg.version is None
    assert len(cfg.searches) == 1


def test_parse_valid_minimal():
    cfg = parse_searches_yaml(_valid_minimal_yaml())
    assert len(cfg.searches) == 1
    s = cfg.searches[0]
    assert s.id == "s1"
    assert s.name == "Search one"
    assert s.keywords == ("a", "b")
    assert len(s.sources) == 1
    src = s.sources[0]
    assert src.adapter == "rss"
    assert src.label == "L1"
    assert src.params["url"] == "https://example.com/feed.xml"


def test_invalid_yaml_syntax():
    raw = "searches: [broken"
    with pytest.raises(ConfigError, match="invalid YAML"):
        parse_searches_yaml(raw)


def test_empty_file_safe_load_none():
    with pytest.raises(ConfigError, match="empty"):
        parse_searches_yaml("")


def test_root_not_mapping():
    with pytest.raises(ConfigError, match="root must be a mapping"):
        parse_searches_yaml("[]")


def test_missing_searches_key():
    with pytest.raises(ConfigError, match="missing required key 'searches'"):
        parse_searches_yaml("version: 1")


def test_searches_empty_list():
    with pytest.raises(ConfigError, match="searches must not be empty"):
        parse_searches_yaml("searches: []")


def test_search_missing_id():
    raw = textwrap.dedent(
        """
        searches:
          - name: "x"
            keywords: [k]
            sources:
              - adapter: rss
                label: L
                url: https://example.com/a.xml
        """
    )
    with pytest.raises(ConfigError, match="missing required key 'id'"):
        parse_searches_yaml(raw)


def test_keywords_empty():
    raw = textwrap.dedent(
        """
        searches:
          - id: a
            name: "x"
            keywords: []
            sources:
              - adapter: rss
                label: L
                url: https://example.com/a.xml
        """
    )
    with pytest.raises(ConfigError, match="keywords must not be empty"):
        parse_searches_yaml(raw)


def test_keyword_empty_string():
    raw = textwrap.dedent(
        """
        searches:
          - id: a
            name: "x"
            keywords: ["ok", "  "]
            sources:
              - adapter: rss
                label: L
                url: https://example.com/a.xml
        """
    )
    with pytest.raises(ConfigError, match="keywords\\[1\\]"):
        parse_searches_yaml(raw)


def test_unknown_adapter_lists_allowed():
    raw = textwrap.dedent(
        """
        searches:
          - id: a
            name: "x"
            keywords: [k]
            sources:
              - adapter: not_real
                label: L
                url: https://example.com/a.xml
        """
    )
    with pytest.raises(ConfigError, match="unknown adapter") as ei:
        parse_searches_yaml(raw)
    msg = str(ei.value)
    assert "html_selectors" in msg
    assert "rss" in msg


def test_unsupported_version():
    raw = textwrap.dedent(
        """
        version: 99
        searches:
          - id: a
            name: "x"
            keywords: [k]
            sources:
              - adapter: rss
                label: L
                url: https://example.com/a.xml
        """
    )
    with pytest.raises(ConfigError, match="unsupported config version"):
        parse_searches_yaml(raw)


def test_rss_missing_url():
    raw = textwrap.dedent(
        """
        searches:
          - id: a
            name: "x"
            keywords: [k]
            sources:
              - adapter: rss
                label: L
        """
    )
    with pytest.raises(ConfigError, match="missing required key 'url'"):
        parse_searches_yaml(raw)


def test_html_selectors_missing_item():
    raw = textwrap.dedent(
        """
        searches:
          - id: a
            name: "x"
            keywords: [k]
            sources:
              - adapter: html_selectors
                label: L
                url: https://example.com/p
                title: h2
                link: a
        """
    )
    with pytest.raises(ConfigError, match="missing required key 'item'"):
        parse_searches_yaml(raw)


def test_unknown_top_level_key():
    raw = textwrap.dedent(
        """
        version: 1
        extra_stuff: true
        searches:
          - id: a
            name: "x"
            keywords: [k]
            sources:
              - adapter: rss
                label: L
                url: https://example.com/a.xml
        """
    )
    with pytest.raises(ConfigError, match="unknown top-level keys"):
        parse_searches_yaml(raw)


def test_load_searches_file_not_found(tmp_path):
    missing = tmp_path / "nope.yaml"
    with pytest.raises(ConfigError, match="Cannot read config file"):
        load_searches(missing)


def test_rss_link_base_empty_string_invalid():
    raw = textwrap.dedent(
        """
        searches:
          - id: a
            name: "x"
            keywords: [k]
            sources:
              - adapter: rss
                label: L
                url: https://example.com/a.xml
                link_base: "   "
        """
    )
    with pytest.raises(ConfigError, match="link_base"):
        parse_searches_yaml(raw)


def test_load_searches_ok(tmp_path):
    p = tmp_path / "searches.yaml"
    p.write_text(_valid_minimal_yaml(), encoding="utf-8")
    cfg = load_searches(p)
    assert cfg.searches[0].id == "s1"


def test_load_searches_example_from_repo():
    """Epic 6: committed example must stay valid for copy-paste onboarding."""
    root = Path(__file__).resolve().parents[1]
    example = root / "searches.example.yaml"
    cfg = load_searches(example)
    assert len(cfg.searches) >= 1
    assert {s.id for s in cfg.searches} >= {"python_jobs_rss", "demo_html_catalog"}
