"""
Load and validate searches.yaml (architecture §5).

Uses only PyYAML + stdlib — no HTTP. Fail-fast on any schema error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from job_raider.exceptions import ConfigError
from job_raider.models import AppConfig, ConfigDefaults, SearchConfig, SourceConfig
from job_raider.sources.registry import ADAPTER_NAMES, list_adapter_names, validate_source_params

SUPPORTED_CONFIG_VERSION = 1


def load_searches(path: str | Path) -> AppConfig:
    """Read file from disk and parse + validate."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Cannot read config file {p}: {e}") from e
    return parse_searches_yaml(text, source_hint=str(p))


def parse_searches_yaml(raw: str, *, source_hint: str = "searches.yaml") -> AppConfig:
    """
    Parse YAML text and validate. Used by tests without touching the filesystem.

    `source_hint` appears in error messages (e.g. file path).
    """
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigError(f"{source_hint}: invalid YAML — {e}") from e

    if data is None:
        raise ConfigError(f"{source_hint}: config is empty")

    if not isinstance(data, Mapping):
        raise ConfigError(f"{source_hint}: root must be a mapping, got {type(data).__name__}")

    version = _optional_version(data, source_hint)
    defaults = _optional_defaults(data, source_hint)
    searches = _parse_searches_list(data, source_hint)

    return AppConfig(searches=searches, version=version, defaults=defaults)


def _optional_version(data: Mapping[str, Any], hint: str) -> int | None:
    if "version" not in data:
        return None
    v = data["version"]
    if not isinstance(v, int) or isinstance(v, bool):
        raise ConfigError(f"{hint}: version must be an integer, got {v!r}")
    if v != SUPPORTED_CONFIG_VERSION:
        raise ConfigError(
            f"{hint}: unsupported config version {v} (supported: {SUPPORTED_CONFIG_VERSION})"
        )
    return v


def _optional_defaults(data: Mapping[str, Any], hint: str) -> ConfigDefaults | None:
    if "defaults" not in data:
        return None
    d = data["defaults"]
    if d is None:
        return None
    if not isinstance(d, Mapping):
        raise ConfigError(f"{hint}: defaults must be a mapping, got {type(d).__name__}")

    timeout = d.get("request_timeout_seconds")
    delay = d.get("polite_delay_ms")
    if timeout is not None and (not isinstance(timeout, int) or isinstance(timeout, bool)):
        raise ConfigError(f"{hint}: defaults.request_timeout_seconds must be an int")
    if delay is not None and (not isinstance(delay, int) or isinstance(delay, bool)):
        raise ConfigError(f"{hint}: defaults.polite_delay_ms must be an int")

    if timeout is None and delay is None:
        return ConfigDefaults()
    return ConfigDefaults(request_timeout_seconds=timeout, polite_delay_ms=delay)


def _parse_searches_list(data: Mapping[str, Any], hint: str) -> tuple[SearchConfig, ...]:
    if "searches" not in data:
        raise ConfigError(f"{hint}: missing required key 'searches'")

    searches_raw = data["searches"]
    if not isinstance(searches_raw, list):
        raise ConfigError(f"{hint}: searches must be a list, got {type(searches_raw).__name__}")
    if len(searches_raw) == 0:
        raise ConfigError(f"{hint}: searches must not be empty")

    unknown_keys = set(data.keys()) - {"version", "defaults", "searches"}
    if unknown_keys:
        raise ConfigError(
            f"{hint}: unknown top-level keys: {', '.join(sorted(unknown_keys))}"
        )

    out: list[SearchConfig] = []
    for i, item in enumerate(searches_raw):
        path = f"{hint} searches[{i}]"
        out.append(_parse_search(item, path))
    return tuple(out)


def _parse_search(item: Any, path: str) -> SearchConfig:
    if not isinstance(item, Mapping):
        raise ConfigError(f"{path}: must be a mapping, got {type(item).__name__}")

    sid = _require_str(item, "id", path)
    name = _require_str(item, "name", path)
    keywords = _parse_keywords(item, path)
    region = _optional_str(item, "region", path)
    max_age_days = _optional_max_age_days(item, path)
    require_keywords = _parse_optional_keyword_list(item, "require_keywords", path)
    exclude_keywords = _parse_optional_keyword_list(item, "exclude_keywords", path)
    sources = _parse_sources(item, path)

    extra = set(item.keys()) - {
        "id",
        "name",
        "keywords",
        "region",
        "sources",
        "max_age_days",
        "require_keywords",
        "exclude_keywords",
    }
    if extra:
        raise ConfigError(f"{path}: unknown keys: {', '.join(sorted(extra))}")

    return SearchConfig(
        id=sid,
        name=name,
        keywords=keywords,
        sources=sources,
        region=region,
        max_age_days=max_age_days,
        require_keywords=require_keywords,
        exclude_keywords=exclude_keywords,
    )


def _require_str(m: Mapping[str, Any], key: str, path: str) -> str:
    if key not in m:
        raise ConfigError(f"{path}: missing required key {key!r}")
    val = m[key]
    if not isinstance(val, str) or not val.strip():
        raise ConfigError(f"{path}: {key!r} must be a non-empty string")
    return val.strip()


def _optional_max_age_days(m: Mapping[str, Any], path: str) -> int | None:
    if "max_age_days" not in m:
        return None
    v = m["max_age_days"]
    if v is None:
        return None
    if not isinstance(v, int) or isinstance(v, bool):
        raise ConfigError(
            f"{path}: max_age_days must be an integer or null, got {type(v).__name__}"
        )
    if v < 1:
        raise ConfigError(f"{path}: max_age_days must be >= 1 when set, got {v}")
    return v


def _optional_str(m: Mapping[str, Any], key: str, path: str) -> str | None:
    if key not in m:
        return None
    val = m[key]
    if val is None:
        return None
    if not isinstance(val, str) or not val.strip():
        raise ConfigError(f"{path}: {key!r} must be a non-empty string when set")
    return val.strip()


def _parse_optional_keyword_list(m: Mapping[str, Any], key: str, path: str) -> tuple[str, ...]:
    """Parse optional ``require_keywords`` / ``exclude_keywords``: list of non-empty strings, or absent/null → ()."""
    if key not in m:
        return ()
    kws = m[key]
    if kws is None:
        return ()
    if not isinstance(kws, list):
        raise ConfigError(
            f"{path}: {key!r} must be a list or null, got {type(kws).__name__}"
        )
    out: list[str] = []
    for j, kw in enumerate(kws):
        if not isinstance(kw, str) or not kw.strip():
            raise ConfigError(f"{path}: {key}[{j}] must be a non-empty string")
        out.append(kw.strip())
    return tuple(out)


def _parse_keywords(m: Mapping[str, Any], path: str) -> tuple[str, ...]:
    if "keywords" not in m:
        raise ConfigError(f"{path}: missing required key 'keywords'")
    kws = m["keywords"]
    if not isinstance(kws, list):
        raise ConfigError(f"{path}: keywords must be a list, got {type(kws).__name__}")
    if len(kws) == 0:
        raise ConfigError(f"{path}: keywords must not be empty")
    out: list[str] = []
    for j, kw in enumerate(kws):
        if not isinstance(kw, str) or not kw.strip():
            raise ConfigError(f"{path}: keywords[{j}] must be a non-empty string")
        out.append(kw.strip())
    return tuple(out)


def _parse_sources(m: Mapping[str, Any], path: str) -> tuple[SourceConfig, ...]:
    if "sources" not in m:
        raise ConfigError(f"{path}: missing required key 'sources'")
    sources_raw = m["sources"]
    if not isinstance(sources_raw, list):
        raise ConfigError(f"{path}: sources must be a list, got {type(sources_raw).__name__}")
    if len(sources_raw) == 0:
        raise ConfigError(f"{path}: sources must not be empty")

    out: list[SourceConfig] = []
    for i, src in enumerate(sources_raw):
        spath = f"{path} sources[{i}]"
        out.append(_parse_source(src, spath))
    return tuple(out)


def _parse_source(item: Any, path: str) -> SourceConfig:
    if not isinstance(item, Mapping):
        raise ConfigError(f"{path}: must be a mapping, got {type(item).__name__}")

    if "adapter" not in item:
        raise ConfigError(f"{path}: missing required key 'adapter'")
    adapter = item["adapter"]
    if not isinstance(adapter, str) or not adapter.strip():
        raise ConfigError(f"{path}: adapter must be a non-empty string")
    adapter = adapter.strip()

    if adapter not in ADAPTER_NAMES:
        allowed = ", ".join(list_adapter_names())
        raise ConfigError(
            f"{path}: unknown adapter {adapter!r}. Allowed adapters: {allowed}"
        )

    label = _require_str(item, "label", path)

    params: dict[str, Any] = {}
    for k, v in item.items():
        if k in ("adapter", "label"):
            continue
        params[k] = v

    validate_source_params(adapter, params, path=path)

    return SourceConfig(adapter=adapter, label=label, params=params)


__all__ = [
    "SUPPORTED_CONFIG_VERSION",
    "load_searches",
    "parse_searches_yaml",
]
