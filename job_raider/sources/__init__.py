"""
Source adapters package.

- **E1:** ``registry`` — YAML validation (no HTTP).
- **E2:** ``adapters.get_adapter`` — runtime fetch implementations.
"""

from job_raider.sources.base import SourceAdapter, SourceContext
from job_raider.sources.registry import (
    ADAPTER_NAMES,
    list_adapter_names,
    validate_source_params,
)

__all__ = [
    "ADAPTER_NAMES",
    "SourceAdapter",
    "SourceContext",
    "list_adapter_names",
    "validate_source_params",
]
