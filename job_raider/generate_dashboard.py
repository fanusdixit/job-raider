"""
Static ``index.html`` from ``ResultsDocument`` (architecture §9–11, Epic 5 Story 5.1).
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from job_raider.models import OpportunityRecord, ResultsDocument, SearchResults

ROME = ZoneInfo("Europe/Rome")
NEW_WINDOW_HOURS = 48

_CSS = """
:root { font-family: system-ui, sans-serif; color: #1a1a1a; background: #fafafa; }
body { max-width: 960px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
h1 { font-size: 1.35rem; font-weight: 600; margin-bottom: 0.25rem; }
.meta { color: #555; font-size: 0.85rem; margin-bottom: 2rem; }
section { margin-bottom: 2.25rem; }
section h2 { font-size: 1.1rem; border-bottom: 1px solid #ccc; padding-bottom: 0.35rem; }
ul { list-style: none; padding: 0; margin: 0; }
li {
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  gap: 0.75rem;
  align-items: baseline;
  padding: 0.6rem 0;
  border-bottom: 1px solid #eee;
}
@media (max-width: 700px) {
  li { grid-template-columns: 1fr; gap: 0.25rem; }
}
.badge {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  background: #e8f4ea;
  color: #1b5e20;
  margin-right: 0.35rem;
  vertical-align: middle;
}
.badge--new { background: #e3f2fd; color: #0d47a1; }
.muted { color: #666; font-size: 0.88rem; }
footer { margin-top: 2rem; font-size: 0.8rem; color: #777; }
"""


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def is_new_badge(published_at: str | None, generated_at: str) -> bool:
    """True if published_at is non-null and within 48h of generated_at in Europe/Rome (PRD §1.1)."""
    if not published_at or not str(published_at).strip():
        return False
    try:
        pub = _parse_iso(published_at.strip())
    except ValueError:
        return False
    try:
        gen = _parse_iso(generated_at.strip())
    except ValueError:
        return False

    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=ROME)
    pub_r = pub.astimezone(ROME)
    gen_r = gen.astimezone(ROME)
    delta = gen_r - pub_r
    return timedelta(0) <= delta <= timedelta(hours=NEW_WINDOW_HOURS)


def format_date_display(published_at: str | None) -> str:
    """Human-readable date in Europe/Rome, or em dash if unknown."""
    if not published_at or not str(published_at).strip():
        return "—"
    try:
        dt = _parse_iso(published_at.strip())
    except ValueError:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ROME)
    dt_r = dt.astimezone(ROME)
    return dt_r.strftime("%Y-%m-%d %H:%M")


def safe_href(url: str) -> str | None:
    """Return HTML-escaped URL safe for href, or None if not http(s)."""
    u = (url or "").strip()
    if u.startswith("http://") or u.startswith("https://"):
        return html.escape(u, quote=True)
    return None


def _render_item(it: OpportunityRecord, doc: ResultsDocument) -> str:
    esc_title = html.escape(it.title)
    esc_source = html.escape(it.source)
    date_txt = format_date_display(it.published_at)
    esc_date = html.escape(date_txt)
    href = safe_href(it.url)
    show_new = is_new_badge(it.published_at, doc.generated_at)
    badge = '<span class="badge badge--new">New</span>' if show_new else ""

    if href:
        title_html = f'{badge}<a href="{href}" rel="noopener noreferrer">{esc_title}</a>'
        link_html = f'<a href="{href}" class="muted" rel="noopener noreferrer">Apri</a>'
    else:
        title_html = f"{badge}{esc_title}"
        link_html = f'<span class="muted">{html.escape(it.url)}</span>'

    return (
        f"<li>"
        f"<div>{title_html}</div>"
        f'<span class="muted">{esc_source}</span>'
        f"<span>{esc_date}</span>"
        f"<span>{link_html}</span>"
        f"</li>"
    )


def _render_section(block: SearchResults, doc: ResultsDocument) -> str:
    esc_name = html.escape(block.name)
    esc_id = html.escape(block.id, quote=True)
    items_html = "".join(_render_item(it, doc) for it in block.items)
    if not items_html:
        items_html = '<p class="muted">Nessun risultato.</p>'
    else:
        items_html = f"<ul>{items_html}</ul>"
    return f'<section id="{esc_id}"><h2>{esc_name}</h2>{items_html}</section>'


def build_index_html(doc: ResultsDocument) -> str:
    """Full single-file HTML with inline CSS (offline-friendly)."""
    esc_gen = html.escape(doc.generated_at)
    esc_ver = html.escape(doc.tool_version)
    sections = "".join(_render_section(s, doc) for s in doc.searches)
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Job Raider — Dashboard</title>
  <style>{_CSS}</style>
</head>
<body>
  <header>
    <h1>Job Raider</h1>
    <p class="meta">Aggiornato: <time datetime="{esc_gen}">{esc_gen}</time> UTC · v{esc_ver}</p>
  </header>
  <main>
    {sections}
  </main>
  <footer>
    Date di pubblicazione mostrate in <strong>Europe/Rome</strong> dove applicabile.
    Badge &quot;New&quot;: pubblicato negli ultimi 48 ore (riferimento ora di generazione, Europe/Rome).
  </footer>
</body>
</html>
"""


def write_index_html(path: str | Path, doc: ResultsDocument) -> None:
    """Write UTF-8 ``index.html``."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(build_index_html(doc), encoding="utf-8")
