# Job Raider

Configurable Python scraper for Italian job and tender signals, with a static HTML dashboard (Phase 1).

**Python:** 3.11+ (per PRD / Epic 1; `requires-python` in `pyproject.toml`).

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Runtime dependencies: `requests`, `beautifulsoup4`, `feedparser`, `PyYAML` (see `pyproject.toml` / `requirements.txt`).

**Editable install** requires **Python 3.11+**. To run tests without an editable install:  
`pip install -r requirements-dev.txt && PYTHONPATH=. pytest`

## Run

```bash
cp searches.example.yaml searches.yaml   # or your own valid YAML
python run.py
python run.py my-config.yaml --results out/results.json --index out/index.html
python run.py -v   # debug logs on stderr
```

**Outputs (defaults):** `./results.json` and `./index.html`. Open `index.html` in a browser (`file://` is fine).

- **Exit `0`:** both files were written. Partial source failures still yield **`0`** if merge + render succeed; check stderr logs.
- **Exit `1`:** invalid config, unreadable/corrupt `results.json`, or an IO error writing outputs.

### Terms of use, robots, and responsibility

Job Raider performs **HTTP GET** requests only to URLs **you** list. You are responsible for complying with each site’s **terms of service**, **robots.txt** rules, and applicable law. The tool applies a **per-run `robots.txt` check** (see `job_raider.robots`) before fetching; failures to retrieve robots are logged and the fetch may still proceed—do not rely on this as legal clearance. Prefer **official RSS feeds** and sources that explicitly allow aggregation.

### Troubleshooting

| Issue | What to do |
|--------|------------|
| **Invalid YAML / config errors** | stderr includes the file path and key (e.g. `searches[0]`, `sources[1]`). Fix the YAML; see [docs/configuration.md](docs/configuration.md). No network is used until config validates. |
| **Corrupt `results.json`** | You should see `ResultsLoadError` or invalid JSON in the message. Delete the file or repair JSON; see [docs/results-schema.md](docs/results-schema.md). |
| **Empty sections** | Keywords use **OR** matching on title/summary; tighten or broaden `keywords`, or check logs for adapter errors. |

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/configuration.md](docs/configuration.md) | `searches.yaml` schema, adapters, keywords, fail-fast rules |
| [docs/results-schema.md](docs/results-schema.md) | `results.json` fields, dedupe, retention, sorting |
| [docs/architecture.md](docs/architecture.md) | Link to Phase 1 architecture + PRD/epics paths |

**Planning artifacts:** `_bmad-output/planning-artifacts/` (PRD, architecture, epics).

## Implementation map

- **CLI / pipeline:** `run.py`, `job_raider.pipeline`  
- **Dashboard:** `job_raider.generate_dashboard` (`build_index_html` / `write_index_html`); optional alias `job_raider.render`  
- **Config:** `job_raider.config.load_searches`  
- **Adapters / HTTP:** `job_raider.sources`, `job_raider.http_client`

## Tests

```bash
pytest
```

From the repo root with dev dependencies installed. The suite includes unit tests plus **integration-style** cases (mocked RSS XML and `robots.txt` via `urllib`, no live scraping).
