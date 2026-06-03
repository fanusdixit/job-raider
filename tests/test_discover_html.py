"""Tests for discover_html.py (offline fixtures)."""

from __future__ import annotations

from pathlib import Path

from discover_html import (
    detect_listing_selectors,
    format_playwright_ok,
    school_path_candidates,
)

FIX_ALBO = Path(__file__).resolve().parent / "fixtures" / "albo_pretorio.html"


def test_school_path_candidates_from_homepage() -> None:
    paths = school_path_candidates("https://www.scuola.edu.it/")
    assert "https://www.scuola.edu.it/albo-pretorio/" in paths
    assert "https://www.scuola.edu.it/circolari/" in paths


def test_school_path_candidates_keeps_explicit_path() -> None:
    paths = school_path_candidates("https://www.scuola.edu.it/albo-pretorio")
    assert paths[0].startswith("https://www.scuola.edu.it/albo-pretorio")


def test_detect_listing_selectors_albo_fixture() -> None:
    html = FIX_ALBO.read_bytes()
    suggestion = detect_listing_selectors(html, "https://www.scuola.edu.it/albo-pretorio/")
    assert suggestion is not None
    assert suggestion.item_count == 2
    assert suggestion.item == ".albo-pretorio .documento"
    assert suggestion.title == "a.titolo"
    assert "item=" in format_playwright_ok(suggestion)


def test_detect_listing_selectors_no_match() -> None:
    assert detect_listing_selectors(b"<html><body><p>empty</p></body></html>", "https://x/") is None
