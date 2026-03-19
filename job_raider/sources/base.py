"""
Adapter protocol and per-fetch context (architecture §6.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from job_raider.models import RawItem

if TYPE_CHECKING:
    from job_raider.http_client import HttpClient


@dataclass(frozen=True)
class SourceContext:
    """Arguments passed to a source adapter for one fetch."""

    search_id: str
    search_name: str
    expanded_keywords: tuple[str, ...]
    region: str | None
    source_label: str
    params: dict[str, Any]


@runtime_checkable
class SourceAdapter(Protocol):
    """Pluggable source: RSS, HTML selectors, etc."""

    name: str
    supports_native_region: bool

    def fetch(self, ctx: SourceContext, http: HttpClient) -> list[RawItem]:
        """Return zero or more raw rows; raise AdapterError on total source failure."""
        ...
