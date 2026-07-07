"""
Core domain types (architecture §6, §10).

`dedupe_id` is typically `compute_dedupe_id(url)` from `job_raider.dedupe`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ConfigDefaults:
    """Optional global defaults from searches.yaml."""

    request_timeout_seconds: int | None = None
    polite_delay_ms: int | None = None
    ai_filter_model: str | None = None


@dataclass(frozen=True)
class SourceConfig:
    """One source under a search (`adapter`, `label`, plus adapter params)."""

    adapter: str
    label: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchConfig:
    """One monitored search from searches.yaml."""

    id: str
    name: str
    keywords: tuple[str, ...]
    sources: tuple[SourceConfig, ...]
    region: str | None = None
    max_age_days: int | None = None
    require_keywords: tuple[str, ...] = field(default_factory=tuple)
    exclude_keywords: tuple[str, ...] = field(default_factory=tuple)
    ai_filter: bool = False


@dataclass(frozen=True)
class AppConfig:
    """Validated root config."""

    searches: tuple[SearchConfig, ...]
    version: int | None = None
    defaults: ConfigDefaults | None = None


@dataclass
class RawItem:
    """Unnormalized row from an adapter before keyword filter / merge."""

    title: str
    url: str
    summary: str | None = None
    published_at: datetime | None = None


@dataclass
class Opportunity:
    """Normalized opportunity stored in results.json / used by render."""

    dedupe_id: str
    title: str
    source: str
    url: str
    search_id: str
    search_name: str
    published_at: datetime | None = None
    last_seen_at: datetime | None = None


@dataclass
class OpportunityRecord:
    """Serialized shape for results.json items (ISO date strings at rest)."""

    dedupe_id: str
    title: str
    source: str
    url: str
    published_at: str | None
    last_seen_at: str
    search_id: str
    search_name: str


@dataclass
class SearchResults:
    """One search block inside results.json."""

    id: str
    name: str
    items: list[OpportunityRecord]


@dataclass(frozen=True)
class SourceRunRecord:
    """One source fetch outcome from the latest pipeline run (for dashboard report)."""

    search_id: str
    search_name: str
    source_label: str
    status: str  # "ok" | "error"
    item_count: int
    error_detail: str | None = None


@dataclass
class RunMeta:
    """Top-level metadata for a persisted run (results.json)."""

    schema_version: int
    generated_at: str  # ISO 8601 UTC Z
    tool_version: str


@dataclass
class ResultsDocument:
    """Full persisted document (architecture §10)."""

    schema_version: int
    generated_at: str
    tool_version: str
    searches: list[SearchResults]
    source_runs: tuple[SourceRunRecord, ...] = field(default_factory=tuple)
