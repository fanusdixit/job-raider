#!/usr/bin/env python3
"""
Discover and validate RSS feed URLs for Job Raider (standalone helper).

Reads URLs from ``discover.yaml`` and/or CLI, probes each URL (and ``/feed/``
when the path does not already look like a feed), checks robots.txt, validates
RSS/Atom with feedparser, and scores keyword overlap with configured keywords.

With ``--playwright``, also probes common Italian school listing paths for
Playwright / ``html_selectors`` when RSS is unavailable or blocked.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Sequence
from urllib.parse import urljoin, urlparse

import feedparser
import yaml

from discover_html import (
    SelectorSuggestion,
    detect_listing_selectors,
    format_playwright_ok,
    school_path_candidates,
    selectors_as_dict,
)
from job_raider.http_client import USER_AGENT, HttpClient
from job_raider.matching import matches_raw_item
from job_raider.models import RawItem
from job_raider.robots import RobotsPolicy

FeedStatus = Literal["ok", "error", "malformed", "robots"]
PlaywrightStatus = Literal["ok", "blocked", "no-match", "skipped"]


@dataclass(frozen=True)
class DiscoverFileConfig:
    """Shape of optional ``discover.yaml``."""

    urls: tuple[str, ...]
    keywords: tuple[str, ...]


@dataclass
class ProbeResult:
    """Outcome for one input URL after trying feed candidates."""

    input_url: str
    resolved_feed_url: str | None
    status: FeedStatus
    item_count: int
    keyword_match_count: int | None
    detail: str
    playwright: PlaywrightStatus | None = None
    playwright_url: str | None = None
    playwright_selectors: dict[str, str] | None = None
    playwright_detail: str | None = None
    playwright_item_count: int | None = None


def load_discover_yaml(path: Path) -> DiscoverFileConfig:
    """Load URLs and keywords from a YAML file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: root must be a mapping")

    urls_raw = raw.get("urls") or []
    if not isinstance(urls_raw, list):
        raise ValueError(f"{path}: urls must be a list")
    urls = tuple(str(u).strip() for u in urls_raw if str(u).strip())

    kw_raw = raw.get("keywords") or []
    if not isinstance(kw_raw, list):
        raise ValueError(f"{path}: keywords must be a list")
    keywords = tuple(str(k).strip() for k in kw_raw if str(k).strip())

    return DiscoverFileConfig(urls=urls, keywords=keywords)


def _path_looks_like_feed(path: str) -> bool:
    p = path.rstrip("/").lower()
    if not p or p == "/":
        return False
    return (
        "/feed" in p
        or "rss" in p
        or p.endswith(".xml")
        or p.endswith(".rss")
        or "atom" in p
    )


def feed_candidates(url: str) -> list[str]:
    """Return the input URL plus ``.../feed/`` when path does not look like a feed."""
    u = url.strip()
    out: list[str] = [u]
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        return out
    if _path_looks_like_feed(parsed.path):
        return out
    extra = urljoin(u.rstrip("/") + "/", "feed/")
    if extra != u and extra not in out:
        out.append(extra)
    return out


def _entry_link(entry: dict[str, Any]) -> str | None:
    link = entry.get("link")
    if link and str(link).strip():
        return str(link).strip()
    for lnk in entry.get("links") or []:
        if not isinstance(lnk, dict):
            continue
        href = lnk.get("href")
        if href and str(href).strip():
            return str(href).strip()
    return None


def _entry_title(entry: dict[str, Any]) -> str:
    t = entry.get("title")
    return "" if t is None else str(t).strip()


def _entry_summary(entry: dict[str, Any]) -> str | None:
    for key in ("summary", "description", "subtitle"):
        val = entry.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return None


def raw_items_from_parsed(parsed: Any) -> list[RawItem]:
    """Map feedparser output to ``RawItem`` rows (same rules as the RSS adapter)."""
    items: list[RawItem] = []
    for entry in getattr(parsed, "entries", None) or []:
        if not isinstance(entry, dict):
            entry = dict(entry)
        link = _entry_link(entry)
        if not link:
            continue
        title = _entry_title(entry)
        if not title:
            title = "(no title)"
        items.append(
            RawItem(
                title=title,
                url=link,
                summary=_entry_summary(entry),
                published_at=None,
            )
        )
    return items


def _is_malformed_feed(parsed: Any) -> bool:
    return bool(getattr(parsed, "bozo", False)) and not getattr(parsed, "entries", None)


def _keyword_hits(items: Sequence[RawItem], keywords: tuple[str, ...]) -> int:
    if not keywords:
        return 0
    return sum(1 for it in items if matches_raw_item(it, keywords))


def _failure_status(last_detail: str, saw_robots_block: bool) -> FeedStatus:
    if saw_robots_block and not last_detail.startswith("HTTP"):
        return "robots"
    if "malformed" in last_detail:
        return "malformed"
    return "error"


def _try_parse_feed_body(
    input_url: str,
    candidate: str,
    content: bytes,
    keywords: tuple[str, ...],
) -> tuple[ProbeResult | None, str | None]:
    """On success return ``(result, None)``; on malformed return ``(None, detail)``."""
    parsed = feedparser.parse(content)
    if _is_malformed_feed(parsed):
        exc = getattr(parsed, "bozo_exception", None)
        hint = f" ({exc})" if exc else ""
        return None, f"malformed feed at {candidate}{hint}"

    items = raw_items_from_parsed(parsed)
    kw_hits: int | None = _keyword_hits(items, keywords) if keywords else None
    return (
        ProbeResult(
            input_url=input_url,
            resolved_feed_url=candidate,
            status="ok",
            item_count=len(items),
            keyword_match_count=kw_hits,
            detail="ok",
        ),
        None,
    )


def probe_feed_url(
    input_url: str,
    http: HttpClient,
    robots: RobotsPolicy,
    keywords: tuple[str, ...],
) -> ProbeResult:
    """
    Try feed candidates for ``input_url``; return the first successful RSS/Atom parse.

    Respect robots.txt before each GET. HTTP errors on one candidate continue to the next.
    """
    last_detail = "no candidates"
    saw_robots_block = False

    candidates = feed_candidates(input_url)
    for idx, candidate in enumerate(candidates):
        if not robots.allowed(candidate):
            saw_robots_block = True
            last_detail = f"robots disallow {candidate}"
            continue
        try:
            response = http.get(candidate)
        except Exception as e:
            last_detail = f"HTTP error for {candidate}: {e}"
            continue

        ok_result, bad = _try_parse_feed_body(
            input_url, candidate, response.content, keywords
        )
        if ok_result is not None:
            more = idx < len(candidates) - 1
            if ok_result.item_count == 0 and more:
                last_detail = f"empty feed at {candidate}"
                continue
            return ok_result
        last_detail = bad or last_detail

    st = _failure_status(last_detail, saw_robots_block)
    return ProbeResult(
        input_url=input_url,
        resolved_feed_url=None,
        status=st,
        item_count=0,
        keyword_match_count=None,
        detail=last_detail,
    )


def _rss_usable(feed: ProbeResult) -> bool:
    return feed.status == "ok" and feed.item_count > 0


def _link_base_for(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def probe_playwright_listing(
    input_url: str,
    feed: ProbeResult,
    http: HttpClient,
    robots: RobotsPolicy,
) -> ProbeResult:
    """
    When RSS is missing or blocked, try school listing paths and detect HTML structure.

    Sets ``playwright`` to ``ok`` / ``blocked`` / ``no-match`` / ``skipped``.
    """
    if _rss_usable(feed):
        return ProbeResult(
            **{**asdict(feed), "playwright": "skipped", "playwright_detail": "rss ok"}
        )

    candidates = school_path_candidates(input_url)
    if not candidates:
        return ProbeResult(
            **{
                **asdict(feed),
                "playwright": "no-match",
                "playwright_detail": "invalid base URL",
            }
        )

    allowed = [u for u in candidates if robots.allowed(u)]
    if not allowed:
        return ProbeResult(
            **{
                **asdict(feed),
                "playwright": "blocked",
                "playwright_detail": "robots disallow all school listing paths",
            }
        )

    last_fetch_error = "no listing pattern on allowed paths"
    for page_url in allowed:
        try:
            response = http.get(page_url)
        except Exception as e:
            last_fetch_error = f"HTTP error for {page_url}: {e}"
            continue

        suggestion = detect_listing_selectors(response.content, page_url)
        if suggestion is None:
            continue

        return ProbeResult(
            **{
                **asdict(feed),
                "playwright": "ok",
                "playwright_url": suggestion.page_url,
                "playwright_selectors": selectors_as_dict(suggestion),
                "playwright_item_count": suggestion.item_count,
                "playwright_detail": format_playwright_ok(suggestion),
            }
        )

    return ProbeResult(
        **{**asdict(feed), "playwright": "no-match", "playwright_detail": last_fetch_error}
    )


def playwright_display(result: ProbeResult) -> str:
    """Short label for the ``playwright`` table column."""
    if result.playwright is None:
        return "—"
    if result.playwright == "ok":
        return result.playwright_detail or "ok (suggested selectors)"
    if result.playwright == "skipped":
        return "skipped (rss ok)"
    return result.playwright


def suggest_playwright_lines(results: Sequence[ProbeResult]) -> list[str]:
    """YAML hints for playwright adapter blocks."""
    lines: list[str] = []
    for r in results:
        if r.playwright == "blocked":
            lines.append(f"PLAYWRIGHT BLOCKED {r.input_url} — {r.playwright_detail}")
            continue
        if r.playwright == "no-match" and r.status != "ok":
            lines.append(f"PLAYWRIGHT NO-MATCH {r.input_url} — {r.playwright_detail}")
            continue
        if r.playwright != "ok" or not r.playwright_url or not r.playwright_selectors:
            continue
        sel = r.playwright_selectors
        date_part = f'\n        date: "{sel["date"]}"' if sel.get("date") else ""
        lines.append(
            f"PLAYWRIGHT {r.input_url}\n"
            f"  adapter: playwright\n"
            f'  url: "{r.playwright_url}"\n'
            f'  item: "{sel["item"]}"\n'
            f'  title: "{sel["title"]}"\n'
            f'  link: "{sel["link"]}"{date_part}\n'
            f'  link_base: "{_link_base_for(r.playwright_url)}"'
        )
    return lines


def suggest_lines(results: Sequence[ProbeResult], keywords: tuple[str, ...]) -> list[str]:
    """Short recommendations for updating ``searches.yaml``."""
    lines: list[str] = []
    for r in results:
        if r.status != "ok" or not r.resolved_feed_url:
            lines.append(f"SKIP  {r.input_url} — {r.status}: {r.detail}")
            continue
        if r.item_count == 0:
            lines.append(f"SKIP  {r.input_url} — feed is empty")
            continue
        if keywords and (r.keyword_match_count or 0) == 0:
            lines.append(
                f"MAYBE {r.resolved_feed_url} — {r.item_count} items, "
                f"no keyword hits (tune keywords or skip)"
            )
            continue
        lines.append(
            f"ADD   {r.resolved_feed_url} — {r.item_count} items"
            + (
                f", {r.keyword_match_count} keyword matches"
                if r.keyword_match_count is not None
                else ""
            )
        )
    lines.extend(suggest_playwright_lines(results))
    return lines


def _print_table(
    results: Sequence[ProbeResult],
    keywords: tuple[str, ...],
    *,
    show_playwright: bool,
) -> None:
    """Print a human-readable result table to stdout."""
    if show_playwright:
        print(
            f"{'URL':<36} {'rss':<10} {'items':>5} {'kw':>4} "
            f"{'playwright':<28} detail"
        )
        print("-" * 130)
        for r in results:
            kw_cell = "—" if r.keyword_match_count is None else str(r.keyword_match_count)
            url_show = r.input_url[:35] + "…" if len(r.input_url) > 36 else r.input_url
            pw = playwright_display(r)
            if len(pw) > 27:
                pw = pw[:26] + "…"
            detail = r.detail if r.status != "ok" else (r.playwright_detail or r.detail)
            detail = (detail[:40] + "…") if len(detail) > 43 else detail
            print(
                f"{url_show:<36} {r.status:<10} {r.item_count:>5} {kw_cell:>4} "
                f"{pw:<28} {detail}"
            )
            if r.resolved_feed_url and r.resolved_feed_url != r.input_url:
                print(f"  → rss: {r.resolved_feed_url}")
            if r.playwright_url:
                print(f"  → playwright: {r.playwright_url} ({r.playwright_item_count} rows)")
        print()
    else:
        print(f"{'URL':<44} {'status':<10} {'items':>6} {'kw matches':>10} detail")
        print("-" * 120)
        for r in results:
            kw_cell = "—" if r.keyword_match_count is None else str(r.keyword_match_count)
            url_show = r.input_url[:43] + "…" if len(r.input_url) > 44 else r.input_url
            detail = (r.detail[:50] + "…") if len(r.detail) > 53 else r.detail
            print(
                f"{url_show:<44} {r.status:<10} {r.item_count:>6} {kw_cell:>10} {detail}"
            )
            if r.resolved_feed_url and r.resolved_feed_url != r.input_url:
                print(f"  → resolved: {r.resolved_feed_url}")
        print()
    print("Suggestions for searches.yaml")
    print("-" * 60)
    for line in suggest_lines(results, keywords):
        print(line)


def run_discover(
    urls: Sequence[str],
    keywords: tuple[str, ...],
    *,
    http: HttpClient,
    robots: RobotsPolicy,
    check_playwright: bool = False,
) -> list[ProbeResult]:
    """Probe each URL and return results in order."""
    out: list[ProbeResult] = []
    for u in urls:
        feed = probe_feed_url(u, http, robots, keywords)
        if check_playwright:
            feed = probe_playwright_listing(u, feed, http, robots)
        out.append(feed)
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Discover RSS/Atom feeds for Job Raider (robots + feedparser + keywords)",
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="Site or feed URLs (optional if --file provides urls)",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        default=None,
        help="YAML file with urls: and keywords: (default: discover.yaml if present)",
    )
    parser.add_argument(
        "--keywords",
        default=None,
        help="Comma-separated keywords (overrides file keywords when set)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON on stdout",
    )
    parser.add_argument(
        "--playwright",
        action="store_true",
        help=(
            "When RSS is unavailable or blocked, probe common school listing paths "
            "(/albo-pretorio/, /albo/, …) and suggest CSS selectors (slower)"
        ),
    )
    args = parser.parse_args(argv)

    file_path = args.file
    if file_path is None:
        default = Path("discover.yaml")
        if default.is_file():
            file_path = default

    file_urls: tuple[str, ...] = ()
    file_keywords: tuple[str, ...] = ()
    if file_path is not None:
        if not file_path.is_file():
            print(f"error: file not found: {file_path}", file=sys.stderr)
            return 1
        try:
            cfg = load_discover_yaml(file_path)
        except (yaml.YAMLError, ValueError, OSError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        file_urls = cfg.urls
        file_keywords = cfg.keywords

    cli_keywords: tuple[str, ...] = ()
    if args.keywords:
        cli_keywords = tuple(k.strip() for k in args.keywords.split(",") if k.strip())

    keywords = cli_keywords if cli_keywords else file_keywords
    url_list = list(dict.fromkeys((*file_urls, *(u.strip() for u in args.urls if u.strip()))))

    if not url_list:
        parser.error("no URLs: pass positional URLs or list them under urls: in discover.yaml")

    http = HttpClient()
    robots = RobotsPolicy(USER_AGENT)

    results = run_discover(
        url_list,
        keywords,
        http=http,
        robots=robots,
        check_playwright=args.playwright,
    )

    if args.json:
        payload = {
            "keywords": list(keywords),
            "playwright_enabled": args.playwright,
            "results": [asdict(r) for r in results],
            "suggestions": suggest_lines(results, keywords),
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Keywords: {', '.join(keywords) if keywords else '—'}")
    if args.playwright:
        print("Playwright path probe: enabled")
    print()
    _print_table(results, keywords, show_playwright=args.playwright)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
