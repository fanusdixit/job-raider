"""
End-to-end run: config → fetch → merge → results.json + index.html (architecture §4, Epic 5).
"""

from __future__ import annotations

import logging
from pathlib import Path

from job_raider.config import load_searches
from job_raider.exceptions import AdapterError, ConfigError, ResultsLoadError
from job_raider.generate_dashboard import write_index_html
from job_raider.http_client import DEFAULT_POLITE_DELAY_MS_RANGE, DEFAULT_TIMEOUT, HttpClient, USER_AGENT
from job_raider.matching import build_source_context
from job_raider.merge import merge_run
from job_raider.models import AppConfig, Opportunity, SourceConfig, SourceRunRecord
from job_raider.normalize import normalize_and_filter
from job_raider.robots import RobotsPolicy
from job_raider.sources.adapters import get_adapter
from job_raider.storage import write_results_atomic

logger = logging.getLogger(__name__)


def _fetch_url(source: SourceConfig) -> str | None:
    u = source.params.get("url")
    return u.strip() if isinstance(u, str) and u.strip() else None


def _http_client_for_config(cfg: AppConfig) -> HttpClient:
    timeout: tuple[float, float] | float = DEFAULT_TIMEOUT
    delay_range = DEFAULT_POLITE_DELAY_MS_RANGE
    d = cfg.defaults
    if d is not None:
        if d.request_timeout_seconds is not None:
            t = float(d.request_timeout_seconds)
            timeout = (t, t)
        if d.polite_delay_ms is not None:
            base_ms = max(1000, int(d.polite_delay_ms))
            delay_range = (base_ms, int(base_ms * 1.5))
    return HttpClient(timeout=timeout, polite_delay_ms_range=delay_range)


def _run_record(
    search_id: str,
    search_name: str,
    label: str,
    *,
    status: str,
    item_count: int,
    error_detail: str | None = None,
) -> SourceRunRecord:
    return SourceRunRecord(
        search_id=search_id,
        search_name=search_name,
        source_label=label,
        status=status,
        item_count=item_count,
        error_detail=error_detail,
    )


def collect_opportunities(
    cfg: AppConfig,
    http: HttpClient,
    robots: RobotsPolicy | None = None,
) -> tuple[list[Opportunity], int, tuple[SourceRunRecord, ...]]:
    """
    Execute searches in **YAML order**; each source in YAML order.

    Returns ``(incoming, source_error_count, source_runs)``.
    """
    gate = robots or RobotsPolicy(USER_AGENT)
    incoming: list[Opportunity] = []
    errors = 0
    runs: list[SourceRunRecord] = []

    for search in cfg.searches:
        for source in search.sources:
            label = source.label
            adapter_name = source.adapter
            url = _fetch_url(source)
            if not url:
                logger.error(
                    "search=%s source=%s adapter=%s status=error error=no_url",
                    search.id,
                    label,
                    adapter_name,
                )
                errors += 1
                runs.append(
                    _run_record(
                        search.id,
                        search.name,
                        label,
                        status="error",
                        item_count=0,
                        error_detail="missing url in source params",
                    )
                )
                continue

            if not gate.allowed(url):
                logger.error(
                    "search=%s source=%s adapter=%s status=error error=robots_disallow url=%s",
                    search.id,
                    label,
                    adapter_name,
                    url,
                )
                errors += 1
                runs.append(
                    _run_record(
                        search.id,
                        search.name,
                        label,
                        status="error",
                        item_count=0,
                        error_detail="robots.txt disallows fetch",
                    )
                )
                continue

            try:
                adapter = get_adapter(source.adapter)
                ctx = build_source_context(search, source, adapter)
                raws = adapter.fetch(ctx, http)
                opps = normalize_and_filter(raws, ctx, keywords=ctx.expanded_keywords)
                incoming.extend(opps)
                logger.info(
                    "search=%s source=%s adapter=%s status=ok count=%d",
                    search.id,
                    label,
                    adapter_name,
                    len(opps),
                )
                runs.append(
                    _run_record(
                        search.id,
                        search.name,
                        label,
                        status="ok",
                        item_count=len(opps),
                    )
                )
            except AdapterError as e:
                logger.error(
                    "search=%s source=%s adapter=%s status=error error=%s",
                    search.id,
                    label,
                    adapter_name,
                    e,
                )
                errors += 1
                runs.append(
                    _run_record(
                        search.id,
                        search.name,
                        label,
                        status="error",
                        item_count=0,
                        error_detail=str(e),
                    )
                )
            except Exception as e:
                logger.exception(
                    "search=%s source=%s adapter=%s status=error",
                    search.id,
                    label,
                    adapter_name,
                )
                errors += 1
                runs.append(
                    _run_record(
                        search.id,
                        search.name,
                        label,
                        status="error",
                        item_count=0,
                        error_detail=str(e),
                    )
                )

    return incoming, errors, tuple(runs)


def run(
    *,
    config_path: Path,
    results_path: Path = Path("results.json"),
    index_path: Path = Path("index.html"),
    robots_policy: RobotsPolicy | None = None,
    http_client: HttpClient | None = None,
) -> int:
    """
    Load config, fetch all sources, merge, write JSON + HTML.

    Returns ``0`` on success, ``1`` on config error or IO / results errors.
    """
    try:
        cfg = load_searches(config_path)
    except ConfigError as e:
        logger.error("%s", e)
        return 1
    except OSError as e:
        logger.error("Cannot read config: %s", e)
        return 1

    http = http_client or _http_client_for_config(cfg)
    robots = robots_policy if robots_policy is not None else RobotsPolicy(USER_AGENT)

    incoming, source_errors, source_runs = collect_opportunities(cfg, http, robots)
    if source_errors:
        logger.warning("Completed fetch with %d source error(s)", source_errors)

    try:
        doc = merge_run(
            previous_path=results_path,
            incoming=incoming,
            app_config=cfg,
            source_runs=source_runs,
        )
        write_results_atomic(results_path, doc)
        write_index_html(index_path, doc)
    except ResultsLoadError as e:
        logger.error("results.json error: %s (delete or fix the file to continue)", e)
        return 1
    except OSError as e:
        logger.error("Failed to write outputs: %s", e)
        return 1

    logger.info(
        "Wrote %s (%d searches) and %s",
        results_path,
        len(doc.searches),
        index_path,
    )
    return 0


def run_with_paths(
    config_path: str | Path,
    results_path: str | Path = "results.json",
    index_path: str | Path = "index.html",
) -> int:
    """Convenience wrapper with string paths."""
    return run(
        config_path=Path(config_path),
        results_path=Path(results_path),
        index_path=Path(index_path),
    )
