"""Domain exceptions."""


class ConfigError(ValueError):
    """Invalid searches.yaml or config schema (fail-fast before any HTTP)."""


class AdapterError(Exception):
    """A single source adapter failed (fetch/parse); pipeline may continue with others."""


class NormalizeError(ValueError):
    """Could not normalize a raw item (e.g. invalid URL for dedupe)."""


class ResultsLoadError(ValueError):
    """results.json is missing, invalid JSON, or has an unsupported shape."""
