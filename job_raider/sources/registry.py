"""
Registered adapter ids for searches.yaml (`adapter` field).

Phase 1 built-ins: rss, html_selectors (see architecture §5–6).
"""

from __future__ import annotations

from typing import Any

# Frozen set of adapters we ship or recognize in config validation (E1+).
ADAPTER_NAMES = frozenset({"rss", "html_selectors"})

# Required YAML params per adapter (beyond `adapter` and `label`).
_ADAPTER_REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "rss": ("url",),
    "html_selectors": ("url", "item", "title", "link"),
}


def list_adapter_names() -> list[str]:
    """Sorted for stable error messages."""
    return sorted(ADAPTER_NAMES)


def validate_source_params(adapter: str, params: dict[str, Any], *, path: str) -> None:
    """
    Ensure adapter-specific required keys exist and are non-empty strings.

    `params` is the source dict minus `adapter` and `label`.
    Raises ConfigError from caller context — this raises ValueError for missing keys.
    """
    from job_raider.exceptions import ConfigError

    required = _ADAPTER_REQUIRED_PARAMS.get(adapter)
    if required is None:
        raise ConfigError(
            f"{path}: unknown adapter {adapter!r}. "
            f"Allowed adapters: {', '.join(list_adapter_names())}"
        )
    for key in required:
        if key not in params:
            raise ConfigError(f"{path}: missing required key {key!r} for adapter {adapter!r}")
        val = params[key]
        if val is None or (isinstance(val, str) and not val.strip()):
            raise ConfigError(
                f"{path}: {key!r} must be a non-empty string for adapter {adapter!r}"
            )
        if not isinstance(val, str):
            raise ConfigError(
                f"{path}: {key!r} must be a string for adapter {adapter!r}, got {type(val).__name__}"
            )

    # Optional string params (must be non-empty when present)
    if adapter == "rss" and "link_base" in params:
        lb = params["link_base"]
        if lb is not None and (not isinstance(lb, str) or not lb.strip()):
            raise ConfigError(
                f"{path}: link_base must be a non-empty string when set, for adapter {adapter!r}"
            )
