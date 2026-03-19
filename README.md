# Job Raider

Configurable Python scraper for Italian job and tender signals, with a static HTML dashboard (Phase 1).

**Python:** 3.11+ (per PRD / Epic 1).

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Runtime dependencies: `requests`, `beautifulsoup4`, `feedparser`, `PyYAML` (see `pyproject.toml` / `requirements.txt`).

**Editable install** requires **Python 3.11+** (`requires-python` in `pyproject.toml`). To run tests without an editable install:  
`pip install -r requirements-dev.txt && PYTHONPATH=. pytest`

## Epic 1–2 (current)

- **E1:** `python run.py [path/to/searches.yaml]` — loads and validates YAML (**no HTTP** in the CLI path).
- **E2 (library):** `HttpClient`, `get_adapter` (`job_raider.sources.adapters`), RSS fetch, `matching`, `normalize` — use from code/tests until the E5 pipeline wires them.
- **E3 (library):** `merge_run`, `load_results_state`, `write_results_atomic` (`job_raider.merge`, `job_raider.storage`) — see `docs/results-schema.md`.

```bash
cp searches.example.yaml searches.yaml   # or your own valid YAML
python run.py
```

Invalid config → exit code `1` and message on stderr.

## Tests

```bash
pytest
```

## Docs

- PRD: `_bmad-output/planning-artifacts/prd-job-raider.md`
- Architecture: `_bmad-output/planning-artifacts/architecture-job-raider-phase1.md`
