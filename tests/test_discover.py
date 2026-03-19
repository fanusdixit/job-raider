"""Tests for discover.py (offline; HTTP and robots mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import discover
from discover import (
    DiscoverFileConfig,
    ProbeResult,
    feed_candidates,
    load_discover_yaml,
    probe_feed_url,
    raw_items_from_parsed,
    run_discover,
    suggest_lines,
)
from job_raider.http_client import HttpClient

FIXTURE_FEED = Path(__file__).resolve().parent / "fixtures" / "sample_feed.xml"


@pytest.fixture(autouse=True)
def _no_polite_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("job_raider.http_client.time.sleep", lambda *_a, **_k: None)


class _AllowRobots:
    def allowed(self, url: str) -> bool:
        return True


class _DenyRobots:
    def allowed(self, url: str) -> bool:
        return False


class _MapHttp:
    def __init__(self, mapping: dict[str, bytes]) -> None:
        self.mapping = mapping

    def get(self, url: str) -> MagicMock:
        body = self.mapping[url]
        r = MagicMock()
        r.content = body
        return r


class _SeqHttp:
    def __init__(self, bodies: list[bytes]) -> None:
        self._bodies = list(bodies)

    def get(self, url: str) -> MagicMock:
        if not self._bodies:
            raise RuntimeError("no more mocked responses")
        body = self._bodies.pop(0)
        r = MagicMock()
        r.content = body
        return r


def test_load_discover_yaml_ok(tmp_path: Path) -> None:
    p = tmp_path / "d.yaml"
    p.write_text(
        "urls:\n  - https://a.example\nkeywords:\n  - python\n",
        encoding="utf-8",
    )
    cfg = load_discover_yaml(p)
    assert cfg == DiscoverFileConfig(
        urls=("https://a.example",),
        keywords=("python",),
    )


def test_load_discover_yaml_root_not_mapping_fails(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- not a dict\n", encoding="utf-8")
    with pytest.raises(ValueError, match="root must be a mapping"):
        load_discover_yaml(p)


def test_load_discover_yaml_urls_not_list_fails(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("urls: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="urls must be a list"):
        load_discover_yaml(p)


def test_load_discover_yaml_keywords_not_list_fails(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("urls: []\nkeywords: python\n", encoding="utf-8")
    with pytest.raises(ValueError, match="keywords must be a list"):
        load_discover_yaml(p)


def test_feed_candidates_adds_feed_path() -> None:
    assert feed_candidates("https://jobs.example/careers") == [
        "https://jobs.example/careers",
        "https://jobs.example/careers/feed/",
    ]


def test_feed_candidates_no_duplicate_for_feed_like_path() -> None:
    u = "https://blog.example/feed/"
    assert feed_candidates(u) == [u]


def test_raw_items_from_parsed_fixture() -> None:
    import feedparser

    parsed = feedparser.parse(FIXTURE_FEED.read_bytes())
    items = raw_items_from_parsed(parsed)
    assert len(items) == 3


def test_probe_feed_ok() -> None:
    body = FIXTURE_FEED.read_bytes()
    http = _MapHttp(
        {
            "https://x/jobs/": b"<html>not a feed</html>",
            "https://x/jobs/feed/": body,
        }
    )
    r = probe_feed_url(
        "https://x/jobs/",
        http,  # type: ignore[arg-type]
        _AllowRobots(),
        ("python",),
    )
    assert r.status == "ok"
    assert r.resolved_feed_url == "https://x/jobs/feed/"
    assert r.item_count == 3
    assert r.keyword_match_count == 1


def test_probe_feed_robots() -> None:
    http = _MapHttp({})
    r = probe_feed_url(
        "https://x/jobs/",
        http,  # type: ignore[arg-type]
        _DenyRobots(),
        (),
    )
    assert r.status == "robots"
    assert r.item_count == 0


def test_probe_feed_malformed_then_ok() -> None:
    body_ok = FIXTURE_FEED.read_bytes()
    http = _SeqHttp([b"not xml at all", body_ok])
    r = probe_feed_url(
        "https://x/jobs/",
        http,  # type: ignore[arg-type]
        _AllowRobots(),
        (),
    )
    assert r.status == "ok"
    assert r.resolved_feed_url == "https://x/jobs/feed/"


def test_probe_feed_http_error() -> None:
    class _ErrHttp:
        def get(self, url: str) -> None:
            raise OSError("network down")

    r = probe_feed_url(
        "https://x/jobs/",
        _ErrHttp(),  # type: ignore[arg-type]
        _AllowRobots(),
        (),
    )
    assert r.status == "error"
    assert "HTTP error" in r.detail


def test_probe_feed_malformed_only() -> None:
    bad = b"<<<"
    http = _SeqHttp([bad, bad])
    r = probe_feed_url(
        "https://x/jobs/",
        http,  # type: ignore[arg-type]
        _AllowRobots(),
        (),
    )
    assert r.status == "malformed"


def test_run_discover_order() -> None:
    body = FIXTURE_FEED.read_bytes()
    junk = b"<html>not a feed</html>"
    http = _MapHttp(
        {
            "https://a/": junk,
            "https://a/feed/": body,
            "https://b/": junk,
            "https://b/feed/": body,
        }
    )
    out = run_discover(["https://a/", "https://b/"], ("java",), http=http, robots=_AllowRobots())  # type: ignore[arg-type]
    assert len(out) == 2
    assert {x.keyword_match_count for x in out} == {1}


def test_suggest_lines_add_and_skip() -> None:
    ok = ProbeResult(
        input_url="https://a/",
        resolved_feed_url="https://a/feed/",
        status="ok",
        item_count=3,
        keyword_match_count=2,
        detail="ok",
    )
    bad = ProbeResult(
        input_url="https://b/",
        resolved_feed_url=None,
        status="error",
        item_count=0,
        keyword_match_count=None,
        detail="oops",
    )
    lines = suggest_lines([ok, bad], ("python",))
    assert any(l.startswith("ADD") for l in lines)
    assert any("SKIP" in l and "b" in l for l in lines)


def test_main_json_stdout(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    body = FIXTURE_FEED.read_bytes()
    junk = b"<html>not a feed</html>"

    class _LocalHttp(HttpClient):
        def get(self, url: str) -> MagicMock:
            r = MagicMock()
            r.content = body if "/feed/" in url else junk
            return r

    cfg = tmp_path / "d.yaml"
    cfg.write_text(
        'urls:\n  - "https://example.com/jobs/"\nkeywords:\n  - python\n',
        encoding="utf-8",
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(discover, "HttpClient", lambda: _LocalHttp())
    monkeypatch.setattr(discover, "RobotsPolicy", lambda _ua: _AllowRobots())
    code = discover.main(["--json", "-f", str(cfg)])
    monkeypatch.undo()
    assert code == 0
    raw = capsys.readouterr().out
    assert "results" in raw
    assert "suggestions" in raw
