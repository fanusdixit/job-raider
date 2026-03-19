"""
Merge, 30-day prune, and deterministic sort for results.json (architecture §8–10, Epic 3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from job_raider import __version__
from job_raider.exceptions import ResultsLoadError
from job_raider.models import (
    AppConfig,
    Opportunity,
    OpportunityRecord,
    ResultsDocument,
    SearchConfig,
    SearchResults,
    SourceRunRecord,
)

SCHEMA_VERSION = 1
RETENTION = timedelta(days=30)


@dataclass
class _StoredEntry:
    """In-memory row while merging (before JSON serialization)."""

    dedupe_id: str
    title: str
    source: str
    url: str
    published_at: datetime | None
    last_seen_at: datetime  # timezone-aware UTC
    search_id: str
    search_name: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc_z(dt: datetime) -> str:
    """ISO 8601 UTC with ``Z`` suffix (seconds precision)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    s = dt.replace(microsecond=0).isoformat()
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    return s


def parse_published_at(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ResultsLoadError(f"published_at must be string or null, got {type(raw).__name__}")
    s = raw.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as e:
        raise ResultsLoadError(f"Invalid published_at ISO datetime: {raw!r}") from e
    if dt.tzinfo is None:
        # Match renderer semantics (architecture §9): naive → treat as Europe/Rome later; store as-is with UTC assumption risky.
        # For load compatibility, assume UTC for naive stored values.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_last_seen_at(raw: Any) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise ResultsLoadError("last_seen_at must be a non-empty ISO string")
    s = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise ResultsLoadError(f"Invalid last_seen_at: {raw!r}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_results_state(path: Path | None) -> dict[str, dict[str, _StoredEntry]]:
    """
    Load prior ``results.json`` into nested maps ``search_id -> dedupe_id -> entry``.

    Returns empty dict if ``path`` is None, missing file, or zero-byte file (cold start).
    Raises ``ResultsLoadError`` on malformed JSON or invalid schema.
    """
    if path is None:
        return {}
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ResultsLoadError(f"Cannot read {path}: {e}") from e
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ResultsLoadError(f"{path}: invalid JSON ({e})") from e
    return _parse_results_payload(data, hint=str(path))


def _parse_results_payload(data: Any, *, hint: str) -> dict[str, dict[str, _StoredEntry]]:
    if not isinstance(data, Mapping):
        raise ResultsLoadError(f"{hint}: root must be an object")

    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ResultsLoadError(
            f"{hint}: unsupported schema_version {version!r} (expected {SCHEMA_VERSION})"
        )

    searches_raw = data.get("searches")
    if searches_raw is None:
        return {}
    if not isinstance(searches_raw, list):
        raise ResultsLoadError(f"{hint}: searches must be an array")

    state: dict[str, dict[str, _StoredEntry]] = {}
    for i, block in enumerate(searches_raw):
        if not isinstance(block, Mapping):
            raise ResultsLoadError(f"{hint}: searches[{i}] must be an object")
        sid = block.get("id")
        if not isinstance(sid, str) or not sid.strip():
            raise ResultsLoadError(f"{hint}: searches[{i}].id must be a non-empty string")
        sname = block.get("name")
        if not isinstance(sname, str) or not sname.strip():
            raise ResultsLoadError(f"{hint}: searches[{i}].name must be a non-empty string")
        items_raw = block.get("items", [])
        if not isinstance(items_raw, list):
            raise ResultsLoadError(f"{hint}: searches[{i}].items must be an array")

        bucket: dict[str, _StoredEntry] = {}
        for j, item in enumerate(items_raw):
            if not isinstance(item, Mapping):
                raise ResultsLoadError(f"{hint}: searches[{i}].items[{j}] must be an object")
            entry = _parse_item_object(item, path_hint=f"{hint} searches[{i}].items[{j}]")
            bucket[entry.dedupe_id] = entry
        state[sid.strip()] = bucket

    return state


def _parse_item_object(item: Mapping[str, Any], *, path_hint: str) -> _StoredEntry:
    def req_str(key: str) -> str:
        v = item.get(key)
        if not isinstance(v, str) or not v.strip():
            raise ResultsLoadError(f"{path_hint}: missing or invalid {key!r}")
        return v.strip()

    dedupe_id = req_str("dedupe_id")
    title = req_str("title")
    source = req_str("source")
    url = req_str("url")
    search_id = req_str("search_id")
    search_name = req_str("search_name")
    published_at = parse_published_at(item.get("published_at"))
    last_seen_at = parse_last_seen_at(item.get("last_seen_at"))

    return _StoredEntry(
        dedupe_id=dedupe_id,
        title=title,
        source=source,
        url=url,
        published_at=published_at,
        last_seen_at=last_seen_at,
        search_id=search_id,
        search_name=search_name,
    )


def apply_incoming(
    state: dict[str, dict[str, _StoredEntry]],
    incoming: Sequence[Opportunity],
    *,
    run_at: datetime,
) -> None:
    """
    Upsert opportunities seen this run and set ``last_seen_at = run_at`` for each.

    Does not remove entries missing from ``incoming`` (prune handles staleness).
    """
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)
    run_at = run_at.astimezone(timezone.utc)

    for opp in incoming:
        bucket = state.setdefault(opp.search_id, {})
        bucket[opp.dedupe_id] = _StoredEntry(
            dedupe_id=opp.dedupe_id,
            title=opp.title,
            source=opp.source,
            url=opp.url,
            published_at=opp.published_at,
            last_seen_at=run_at,
            search_id=opp.search_id,
            search_name=opp.search_name,
        )


def prune_stale(
    state: dict[str, dict[str, _StoredEntry]],
    *,
    run_at: datetime,
    max_age: timedelta = RETENTION,
) -> None:
    """Drop entries where ``run_at - last_seen_at > max_age`` (in-place)."""
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)
    run_at = run_at.astimezone(timezone.utc)

    for sid, bucket in list(state.items()):
        stale_ids = [
            did
            for did, ent in bucket.items()
            if run_at - ent.last_seen_at > max_age
        ]
        for did in stale_ids:
            del bucket[did]
        if not bucket:
            del state[sid]


def sort_items_for_search(items: list[_StoredEntry]) -> list[_StoredEntry]:
    """
    Sort: dated ``published_at`` descending; null ``published_at`` after all dated;
    tie-break by ``title`` casefold (ascending for null block, ascending for dated ties).
    """
    def key_dated(r: _StoredEntry) -> tuple:
        assert r.published_at is not None
        ts = r.published_at.timestamp()
        return (-ts, r.title.casefold())

    def key_null(r: _StoredEntry) -> tuple:
        return (r.title.casefold(),)

    dated = [r for r in items if r.published_at is not None]
    nulls = [r for r in items if r.published_at is None]
    dated.sort(key=key_dated)
    nulls.sort(key=key_null)
    return dated + nulls


def _entry_to_record(entry: _StoredEntry) -> OpportunityRecord:
    pub = None
    if entry.published_at is not None:
        pub = entry.published_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        if pub.endswith("+00:00"):
            pub = pub[:-6] + "Z"
    return OpportunityRecord(
        dedupe_id=entry.dedupe_id,
        title=entry.title,
        source=entry.source,
        url=entry.url,
        published_at=pub,
        last_seen_at=format_utc_z(entry.last_seen_at),
        search_id=entry.search_id,
        search_name=entry.search_name,
    )


def build_results_document(
    state: dict[str, dict[str, _StoredEntry]],
    *,
    app_config: AppConfig,
    run_at: datetime | None = None,
    tool_version: str | None = None,
    source_runs: tuple[SourceRunRecord, ...] = (),
) -> ResultsDocument:
    """
    Build canonical ``ResultsDocument`` for configured searches only (orphan sections dropped).

    Search blocks are ordered by ``search_id`` ascending. Empty searches still appear.
    """
    if run_at is None:
        run_at = _utc_now()
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)
    run_at = run_at.astimezone(timezone.utc)

    tv = tool_version if tool_version is not None else __version__
    ordered_searches = sorted(app_config.searches, key=lambda s: s.id)

    blocks: list[SearchResults] = []
    for sc in ordered_searches:
        bucket = state.get(sc.id, {})
        items = sort_items_for_search(list(bucket.values()))
        records = [_entry_to_record(e) for e in items]
        blocks.append(
            SearchResults(id=sc.id, name=sc.name, items=records)
        )

    return ResultsDocument(
        schema_version=SCHEMA_VERSION,
        generated_at=format_utc_z(run_at),
        tool_version=tv,
        searches=blocks,
        source_runs=source_runs,
    )


def merge_run(
    *,
    previous_path: Path | None,
    incoming: Sequence[Opportunity],
    app_config: AppConfig,
    run_at: datetime | None = None,
    tool_version: str | None = None,
    source_runs: tuple[SourceRunRecord, ...] = (),
) -> ResultsDocument:
    """
    Full Epic 3 pipeline: load → apply incoming → prune → build sorted document.
    """
    state = load_results_state(previous_path)
    if run_at is None:
        run_at = _utc_now()
    apply_incoming(state, incoming, run_at=run_at)
    prune_stale(state, run_at=run_at)
    return build_results_document(
        state,
        app_config=app_config,
        run_at=run_at,
        tool_version=tool_version,
        source_runs=source_runs,
    )


def document_to_json_dict(doc: ResultsDocument) -> dict[str, Any]:
    """Serialize ``ResultsDocument`` to a JSON-serializable dict."""
    out: dict[str, Any] = {
        "schema_version": doc.schema_version,
        "generated_at": doc.generated_at,
        "tool_version": doc.tool_version,
        "searches": [
            {
                "id": s.id,
                "name": s.name,
                "items": [
                    {
                        "dedupe_id": it.dedupe_id,
                        "title": it.title,
                        "source": it.source,
                        "url": it.url,
                        "published_at": it.published_at,
                        "last_seen_at": it.last_seen_at,
                        "search_id": it.search_id,
                        "search_name": it.search_name,
                    }
                    for it in s.items
                ],
            }
            for s in doc.searches
        ],
    }
    out["source_runs"] = [
        {
            "search_id": r.search_id,
            "search_name": r.search_name,
            "source_label": r.source_label,
            "status": r.status,
            "item_count": r.item_count,
            "error_detail": r.error_detail,
        }
        for r in doc.source_runs
    ]
    return out
