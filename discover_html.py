"""
HTML listing detection for discover.py (Italian school albo / news pages).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from soupsieve.util import SelectorSyntaxError

from job_raider.sources.html_selectors import _href_from_link_element, _title_from_element

SCHOOL_PATH_SUFFIXES: tuple[str, ...] = (
    "albo-pretorio/",
    "albo/",
    "comunicati/",
    "news/",
    "circolari/",
)

# (item, title, link, date) — ordered most-specific first.
LISTING_PATTERNS: tuple[tuple[str, str, str, str | None], ...] = (
    (".albo-pretorio .documento", "a.titolo", "a.titolo", ".data-pubblicazione"),
    (".albo-pretorio .entry", "a", "a", ".data, time"),
    ("#albo-pretorio tbody tr", "a", "a", "td.data, td:last-child"),
    (".elenco-albo > div", "a", "a", ".data"),
    ("article.albo", "h2 a, h3 a", "h2 a, h3 a", "time, .date"),
    ("table.albo tbody tr", "a", "a", "td.data"),
    ("article.post", ".entry-title a", ".entry-title a", ".published, time"),
    (".news-item", "a", "a", ".date, time"),
    ("ul.albo li", "a", "a", "span.data, time"),
    ("tbody tr", "a", "a", "td:last-child"),
    ("article", "h2 a, h3 a", "h2 a, h3 a", "time, .date"),
)


@dataclass(frozen=True)
class SelectorSuggestion:
    """Detected CSS selectors for a playwright / html_selectors source block."""

    page_url: str
    item: str
    title: str
    link: str
    date: str | None
    item_count: int


def school_path_candidates(input_url: str) -> list[str]:
    """Return the input URL (when pathful) plus common school listing paths on the origin."""
    u = input_url.strip()
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        return []

    origin = f"{parsed.scheme}://{parsed.netloc}"
    out: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        if url not in seen:
            seen.add(url)
            out.append(url)

    path = parsed.path.rstrip("/")
    if path and path != "/":
        add(u if u.endswith("/") else u + "/")

    for suffix in SCHOOL_PATH_SUFFIXES:
        add(urljoin(origin + "/", suffix))

    return out


def _score_listing_pattern(
    soup: BeautifulSoup,
    *,
    item_sel: str,
    title_sel: str,
    link_sel: str,
) -> int:
    try:
        nodes = soup.select(item_sel)
    except (ValueError, SelectorSyntaxError):
        return 0

    hits = 0
    for node in nodes:
        if not isinstance(node, Tag):
            continue
        try:
            title_el = node.select_one(title_sel)
            link_el = node.select_one(link_sel)
        except (ValueError, SelectorSyntaxError):
            return 0
        href = _href_from_link_element(link_el if link_el is not None else title_el)
        if not href:
            continue
        title = _title_from_element(title_el if title_el is not None else link_el)
        if not title or title == "(no title)":
            continue
        hits += 1
    return hits


def detect_listing_selectors(html: bytes, page_url: str) -> SelectorSuggestion | None:
    """Pick the best matching listing pattern for ``html``, if any."""
    soup = BeautifulSoup(html, "html.parser")
    best: SelectorSuggestion | None = None
    best_count = 0

    for item_sel, title_sel, link_sel, date_sel in LISTING_PATTERNS:
        count = _score_listing_pattern(
            soup,
            item_sel=item_sel,
            title_sel=title_sel,
            link_sel=link_sel,
        )
        if count > best_count:
            best_count = count
            best = SelectorSuggestion(
                page_url=page_url,
                item=item_sel,
                title=title_sel,
                link=link_sel,
                date=date_sel,
                item_count=count,
            )

    if best is None or best_count < 1:
        return None
    return best


def selectors_as_dict(suggestion: SelectorSuggestion) -> dict[str, str]:
    """YAML-ready selector map."""
    out = {
        "item": suggestion.item,
        "title": suggestion.title,
        "link": suggestion.link,
    }
    if suggestion.date:
        out["date"] = suggestion.date
    return out


def format_playwright_ok(suggestion: SelectorSuggestion) -> str:
    """Human-readable ``playwright`` column value."""
    parts = [
        f"item={suggestion.item}",
        f"title={suggestion.title}",
        f"link={suggestion.link}",
    ]
    if suggestion.date:
        parts.append(f"date={suggestion.date}")
    return f"ok ({', '.join(parts)})"
