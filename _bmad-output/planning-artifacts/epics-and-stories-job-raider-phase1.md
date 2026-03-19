---
workflowType: epics-and-stories
project_name: job-raider
status: phase-1-ready
inputDocuments:
  - _bmad-output/planning-artifacts/prd-job-raider.md (v1.0 locked)
  - _bmad-output/planning-artifacts/architecture-job-raider-phase1.md
date: 2026-03-19
author: John (PM) / Stefanoguida.nearform
implementationOrder: matches architecture §17
---

# Job Raider — Epic & Story Breakdown (Phase 1)

This document decomposes the **locked PRD** and **Phase 1 architecture** into implementable epics and stories. **Implement epics in numeric order** (matches architect §17).

---

## Requirements inventory (summary)

### Functional requirements (from PRD §11)

FR1–FR6 configuration & fail-fast; FR7–FR11 fetch/parse/partial success; FR12–FR15b normalize, dedupe, JSON, retention; FR16–FR20 static dashboard; FR21–FR23 CLI & docs.

### Non-functional requirements (from PRD §12)

NFR1 exit/config ordering; NFR2 bounded timeouts/retries; NFR3 robots.txt; NFR4 politeness; NFR5 ToS warning in docs; NFR6 adapter extensibility; NFR7 docs in `docs/`; NFR8 no secrets; NFR9 HTML escape + safe `href`; NFR10 local performance target.

### Additional / architecture requirements

- Package layout under `job_raider/` + root `run.py` (architecture §3).  
- Canonical `results.json` shape + sorted `items` (architecture §10, §9).  
- Adapter registry keyed by YAML `adapter` string; built-ins `rss`, `html_selectors` (architecture §5–6).  
- Atomic JSON write (ADR-06).  
- Stdlib `zoneinfo` for Europe/Rome badge logic (architecture §9).

### UX (from PRD §10)

Static `index.html`, inline CSS, minimal desktop layout, “New” badge, grouped sections, no external CDN dependency.

### FR coverage map (by epic)

| Epic | Primary FRs | Primary NFRs |
|------|----------------|--------------|
| E1 Foundation | FR1, FR2, FR3 (structure), FR6 | NFR1, NFR7 (stub), NFR8 |
| E2 Fetch RSS + match | FR3, FR4, FR5, FR7, FR9, FR10, FR11 | NFR2, NFR4, NFR6 |
| E3 Merge + storage | FR12–FR15, FR15b | NFR1 (data path) |
| E4 HTML adapter | FR4, FR7, FR8, FR10, FR11 | NFR6 |
| E5 Pipeline + render + CLI | FR16–FR21, FR22 | NFR1, NFR9, NFR10 |
| E6 Docs + example config | FR23, NFR5, NFR7 | — |
| E7 Hardening | FR11 (robots skip), FR22 | NFR2, NFR3, NFR4 |

---

## Epic list

1. **E1 — Foundation:** domain models + `searches.yaml` load/validate (fail-fast, no HTTP).  
2. **E2 — HTTP client + RSS adapter + matching:** registry, first vertical slice of fetch → raw items → keyword OR filter.  
3. **E3 — Merge, retention & atomic storage:** dedupe, `last_seen_at`, 30-day prune, `results.json`.  
4. **E4 — `html_selectors` adapter:** generic BS4 extraction + offline fixtures.  
5. **E5 — Render + pipeline + `run.py`:** `index.html`, orchestration, logging, exit codes.  
6. **E6 — Documentation & example config:** `docs/*`, `searches.example.yaml`, README.  
7. **E7 — Hardening:** robots.txt gate, retry/timeout polish, expanded automated tests.

---

## Epic 1: Foundation — models & config (fail-fast)

**Goal:** Establish the Python package, core types, and strict configuration loading so **invalid YAML never triggers network I/O** (FR6, NFR1).

### Story 1.1: Project scaffold & dependencies

As a **developer**,  
I want **a runnable package layout and declared dependencies**,  
So that **the team can install and import `job_raider` consistently**.

**Acceptance criteria:**

- **Given** a fresh clone, **when** I create a venv and install deps (`requirements.txt` and/or `pyproject.toml`), **then** `python -c "import job_raider"` succeeds.  
- **And** runtime deps match PRD: `requests`, `beautifulsoup4`, `feedparser`, `PyYAML` (+ stdlib).  
- **And** `run.py` exists at repo root and is the documented entry point (may delegate to no-op until E5).  
- **And** Python **3.11+** is stated in README or `pyproject` classifiers.

**Technical notes:** Optional `pytest` as dev dependency per architecture §14.

---

### Story 1.2: Core domain models

As a **developer**,  
I want **typed models for searches, sources, opportunities, and run metadata**,  
So that **downstream modules share one canonical in-memory representation**.

**Acceptance criteria:**

- **Given** architecture §10 and §6, **when** I inspect `job_raider/models.py` (or equivalent), **then** it defines structures for at least: search config, source config, `RawItem`, `Opportunity`, merged result container, run metadata (`generated_at`, `tool_version`, `schema_version`).  
- **And** `published_at` is representable as **optional** (nullable).  
- **And** `dedupe_id` derivation is specified (implemented or delegated to merge module) per architecture §8.1.

---

### Story 1.3: Load & validate `searches.yaml`

As an **operator**,  
I want **clear errors when my config is wrong**,  
So that **I fix YAML before any scraping runs** (FR6, SC6).

**Acceptance criteria:**

- **Given** `searches.yaml` uses `yaml.safe_load` only, **when** the file is syntactically invalid, **then** the program prints a **human-readable** error to stderr and exits **non-zero** **without** importing/using `requests` for fetches.  
- **And** when required fields are missing (`searches` empty, search missing `id`/`name`/`keywords`/`sources`, source missing `adapter`/`label`, empty keyword strings), **then** same fail-fast behavior with a message that identifies the path/key.  
- **And** when `adapter` is unknown, **then** the error lists **allowed** adapter names (registry contents at this phase may be only `rss` until E2—still list them).  
- **And** when `version` is present and unsupported, **then** fail fast with guidance.  
- **And** valid minimal config parses into structured objects for the pipeline.

**Maps to:** FR1, FR2, FR6; architecture §5.

---

### Story 1.4: Automated tests — config failure modes

As a **developer**,  
I want **tests that prove fail-fast config behavior**,  
So that **we never regress into “HTTP before validation.”**

**Acceptance criteria:**

- **Given** tests use invalid/malformed YAML fixtures, **when** validation runs, **then** assertions expect failure **without** HTTP mocks being invoked.  
- **And** at least one test covers unknown `adapter`.  
- **And** tests run with `pytest` (or documented alternative) via one command.

**Maps to:** architecture §14 (config row).

---

## Epic 2: HTTP client + RSS adapter + matching

**Goal:** Introduce **polite HTTP**, the **adapter registry**, the **`rss` adapter**, and **OR keyword + region expansion** so we can produce normalized candidate opportunities from real feeds (FR7, FR9, FR10, FR11; FR3–FR5).

### Story 2.1: HTTP session with timeouts, delays, and retries

As a **developer**,  
I want **a shared HTTP client** with bounded timeouts, retries, and politeness delays,  
So that **runs don’t hang and behave responsibly** (NFR2, NFR4).

**Acceptance criteria:**

- **Given** architecture §7, **when** the client performs GETs, **then** connect/read timeouts are applied (defaults per architecture, e.g. ~30s).  
- **And** idempotent GET retries are **bounded** (e.g. up to 3 attempts) for transient errors (`429`, `503`, connection errors) with backoff (e.g. 0.5s / 1.5s).  
- **And** a **jittered delay** runs between requests globally (default range per architecture).  
- **And** `User-Agent` identifies Job Raider + version.  
- **And** behavior is covered by unit tests with mocked `requests` or a test double where feasible.

---

### Story 2.2: Adapter protocol & registry

As a **developer**,  
I want **a registry that maps YAML `adapter` strings to implementations**,  
So that **adding sources stays modular** (NFR6).

**Acceptance criteria:**

- **Given** architecture §6.1, **when** I register adapters, **then** `rss` resolves to the RSS implementation.  
- **And** unknown adapter strings remain a **config validation** concern at load time (E1) and/or a defensive check before fetch.  
- **And** `SourceContext` carries `search_id`, `search_name`, expanded keywords, `region`, `label`, and params dict.

---

### Story 2.3: `rss` adapter

As an **operator**,  
I want **RSS/Atom sources defined only in YAML**,  
So that **I can ingest feeds without code changes** (FR4, FR9).

**Acceptance criteria:**

- **Given** a source block `{ adapter: rss, label, url }`, **when** the adapter runs, **then** it fetches the URL and parses with `feedparser`.  
- **And** each entry maps to a `RawItem` with title, link, optional summary, optional published time.  
- **And** adapter failures raise or return a structured error consumed by the pipeline (E5) without crashing unrelated sources (FR11)—at minimum, unit-level behavior defined; full wiring in E5.  
- **And** offline tests use committed XML/string fixtures.

---

### Story 2.4: Keyword OR matching & region expansion

As an **operator**,  
I want **OR keyword matching and best-effort region handling**,  
So that **results match the locked PRD semantics** (FR3, FR5).

**Acceptance criteria:**

- **Given** multiple keywords, **when** matching runs, **then** a `RawItem`/`Opportunity` matches if **any** keyword is a **case-insensitive substring** of **title** or **summary** (if present).  
- **And** when `region` is set and an adapter does **not** declare native region support, **then** the region string is included in the **effective keyword list** used for this filter (architecture §6).  
- **And** unit tests cover OR logic, case insensitivity, and region expansion paths.

---

### Story 2.5: Normalize `RawItem` → `Opportunity` + `dedupe_id`

As a **developer**,  
I want **consistent normalization and URL dedupe keys**,  
So that **merge (E3) receives uniform records** (FR12, architecture §8.1).

**Acceptance criteria:**

- **Given** a `RawItem`, **when** normalized, **then** output includes `title`, `source` (label), `url`, `search_id`, `search_name`, optional `published_at`, and `dedupe_id` from **normalized URL** rules in architecture §8.1.  
- **And** relative links resolve with optional `link_base` where applicable (RSS/HTML—HTML base handled in E4).  
- **And** unparseable dates become `null` (will serialize to JSON `null`).

---

## Epic 3: Merge, retention & atomic storage

**Goal:** Implement **stateful** `results.json` with **upsert**, **`last_seen_at` refresh only when seen this run**, **30-day prune**, **deterministic sort**, and **atomic write** (FR12–FR15b, SC3c, SC5).

### Story 3.1: Load or cold-start `results.json`

As a **developer**,  
I want **tolerant loading of prior JSON**,  
So that **first run and upgrades don’t crash** (FR15b).

**Acceptance criteria:**

- **Given** no file, **when** load runs, **then** merge starts from empty state.  
- **And** given malformed JSON, **then** fail with a clear error OR documented reset procedure—pick one and document in `docs/results-schema.md` (recommend **clear error** with hint to delete file).  
- **And** given valid schema_version, **when** loaded, **then** opportunities are addressable by `dedupe_id`.

---

### Story 3.2: Merge upsert & `last_seen_at` rules

As a **developer**,  
I want **merge logic that matches PRD `last_seen_at` semantics**,  
So that **retention and partial runs behave as specified** (FR13, FR13b, FR14).

**Acceptance criteria:**

- **Given** a set of `dedupe_id` seen in the **current run** (post-filter), **when** merge runs, **then** those records get `last_seen_at = run_generated_at` (UTC ISO Z).  
- **And** records **not** seen this run keep their **previous** `last_seen_at` unchanged.  
- **And** upsert refreshes `title`, `url`, `published_at` from latest parse when provided.  
- **And** unit tests demonstrate “seen vs not seen” behavior without network.

---

### Story 3.3: Prune records older than 30 days by `last_seen_at`

As an **operator**,  
I want **stale items removed automatically after 30 days**,  
So that **JSON stays bounded** (FR15, SC3c).

**Acceptance criteria:**

- **Given** `now` and `last_seen_at`, **when** `now - last_seen_at > 30 days`, **then** the record is **dropped** on write.  
- **And** boundary case **≤ 30 days** is **retained** (test the edge).  
- **And** pruning runs **before** atomic write every successful pipeline completion.

---

### Story 3.4: Sort `items` for deterministic output

As a **developer**,  
I want **stable ordering inside each search**,  
So that **git diffs and SC5 hold** (PRD §10.1, architecture §9).

**Acceptance criteria:**

- **Given** merged items for a search, **when** serialized, **then** order is: dated items **descending** by `published_at`; **null** `published_at` **after** all dated items; null block sorted by **title** casefold; dated ties broken by **title** casefold.  
- **And** searches are ordered by **`search_id` ascending** (architecture §9).

---

### Story 3.5: Atomic write of `results.json`

As a **developer**,  
I want **atomic persistence**,  
So that **a crash mid-write doesn’t corrupt the store** (ADR-06).

**Acceptance criteria:**

- **Given** a write operation, **when** persisting, **then** implementation uses temp file in same directory + `os.replace` (or equivalent documented atomic pattern on target OS).  
- **And** JSON is UTF-8 and includes `schema_version`, `generated_at`, `tool_version`, and `searches` per architecture §10.

---

## Epic 4: `html_selectors` adapter

**Goal:** Support **HTML list pages** via YAML-driven selectors (FR8, FR10, FR11; architecture §5–6).

### Story 4.1: Implement `html_selectors` adapter

As an **operator**,  
I want **to scrape listing pages using CSS selectors from YAML**,  
So that **non-RSS sites are configurable without code** (FR4, FR8).

**Acceptance criteria:**

- **Given** params `url`, `item`, `title`, `link`, optional `date`, optional `link_base` (architecture §5), **when** the adapter runs, **then** it GETs the page, parses with BeautifulSoup, iterates `item` nodes, extracts title text, link href, optional date.  
- **And** failures surface as adapter-level errors without killing other sources (FR11) once wired in pipeline.  
- **And** `supports_native_region` is **False** for this adapter (region flows via keyword expansion from E2).

---

### Story 4.2: Offline fixtures & tests for HTML adapter

As a **developer**,  
I want **fixture HTML files**,  
So that **parsing is regression-tested without live sites**.

**Acceptance criteria:**

- **Given** at least **two** HTML fixtures (minimal synthetic pages), **when** tests run, **then** they assert expected `RawItem` counts and key fields.  
- **And** one fixture includes **relative** links requiring `link_base`.

**Maps to:** architecture §17 step 4 & §14.

---

## Epic 5: Render + pipeline + `run.py`

**Goal:** Wire the **full run**, emit **`index.html`**, implement **Europe/Rome 48h badge**, **safe HTML**, and **logging/exit codes** (FR16–FR22, NFR1, NFR9).

### Story 5.1: Render static `index.html`

As an **operator**,  
I want **a single offline-friendly dashboard**,  
So that **I can browse results locally** (FR16–FR20, PRD §10).

**Acceptance criteria:**

- **Given** merged in-memory model or written JSON, **when** render runs, **then** it writes **`index.html`** with **inline CSS**, sections per search (`search_id` order), each item showing **title (linked)**, **source**, **date** (or placeholder for null), **link**.  
- **And** all dynamic text uses **`html.escape`** (NFR9).  
- **And** `href` only emitted for `http://` or `https://`; otherwise render as text-only + log (architecture §13).  
- **And** “New” badge shows **only** when `published_at` non-null and within **48h** of `generated_at` compared in **Europe/Rome** (PRD §1.1, architecture §9).  
- **And** `null` dates: **no badge**; ordering matches Epic 3 sort rules in the page.  
- **And** snapshot-style tests can assert badge presence/absence and ordering using fixture data.

---

### Story 5.2: End-to-end `pipeline.run()` orchestration

As a **developer**,  
I want **one orchestrator** that runs steps in architecture §4 order,  
So that **behavior matches the design document**.

**Acceptance criteria:**

- **Given** valid config, **when** `pipeline.run()` executes, **then** it: validates config (already done before HTTP), builds HTTP client, iterates searches in YAML order, runs each source adapter sequentially, applies matching, collects `seen` ids, merges with previous JSON, prunes, sorts, writes JSON, renders HTML.  
- **And** partial source failure logs **ERROR** and continues (FR11, FR22).  
- **And** per source emits a line with search id, label, adapter, status, and count (architecture §12).  
- **And** **no HTTP** occurs if config validation fails (re-verify integration-style test or trace).

---

### Story 5.3: `run.py` CLI entry & exit codes

As an **operator**,  
I want **`python run.py` to be the primary command**,  
So that **Phase 1 matches the PRD** (FR21, NFR1).

**Acceptance criteria:**

- **Given** valid config and successful write, **when** `python run.py` completes, **then** exit code is **0**.  
- **And** given invalid config, **then** exit **non-zero** **before** network.  
- **And** given unrecoverable IO error writing outputs, **then** exit **non-zero**.  
- **And** partial source errors **still exit 0** if `results.json` and `index.html` are written (architecture §4 step 14).

---

## Epic 6: Documentation & example configuration

**Goal:** Satisfy **FR23** and **NFR7** with operator-facing docs and a safe example YAML.

### Story 6.1: `docs/configuration.md`

As an **operator**,  
I want **documented YAML schema and adapter parameters**,  
So that **I can configure searches without reading source** (NFR7).

**Acceptance criteria:**

- **Given** architecture §5, **when** I read `docs/configuration.md`, **then** it explains top-level keys, `searches[]`, `sources[]`, required fields, `defaults`, and each adapter’s params for `rss` and `html_selectors`.  
- **And** it describes **OR keywords**, **region best-effort**, and **fail-fast** validation behavior.

---

### Story 6.2: `docs/results-schema.md`

As an **operator**,  
I want **a described JSON schema**,  
So that **I can inspect or diff `results.json` confidently**.

**Acceptance criteria:**

- **When** I read `docs/results-schema.md`, **then** it documents fields, `null` `published_at`, `last_seen_at` semantics, retention, sorting, and `dedupe_id` normalization (architecture §8–10).  
- **And** it includes at least one **full minimal example JSON**.

---

### Story 6.3: `searches.example.yaml` + README

As an **operator**,  
I want **a copy-paste example and setup steps**,  
So that **I can run Job Raider quickly** (FR23).

**Acceptance criteria:**

- **Given** `searches.example.yaml`, **when** copied to `searches.yaml`, **then** it validates against the loader (use placeholder URLs or documented test feeds that are polite/low risk).  
- **And** README covers: Python version, venv, install, `python run.py`, opening `index.html`, where outputs go, **ToS/robots** caution (NFR5), and troubleshooting **invalid YAML**.

---

### Story 6.4: Link architecture for contributors

As a **developer**,  
I want **a pointer from `docs/` to the architecture doc**,  
So that **contributors align with Phase 1 decisions**.

**Acceptance criteria:**

- **Given** `docs/` exists, **when** I open `docs/architecture.md` (or README section), **then** it links to `_bmad-output/planning-artifacts/architecture-job-raider-phase1.md` or summarizes “copy in repo” policy agreed by team.

---

## Epic 7: Hardening — robots.txt, tests, polish

**Goal:** Close **NFR3**, tighten **NFR2/NFR4** validation, and expand tests around **prune**, **render**, and **integration** per architecture §17 step 7.

### Story 7.1: `robots.txt` gate per netloc

As an **operator**,  
I want **the tool to respect robots.txt when feasible**,  
So that **we reduce ethical/legal risk** (NFR3).

**Acceptance criteria:**

- **Given** architecture §4 step 4, **before** first GET to a **netloc**, **when** robots is fetched/parsed with `urllib.robotparser`, **then** disallowed URLs are **skipped** with a clear log line for that source.  
- **And** behavior is documented (per-run cache, limitations).  
- **And** tests use a mock robots response or local `file://` pattern **not** used in prod—prefer mocking `robotparser` inputs.

---

### Story 7.2: Integration test — golden path with mocks

As a **developer**,  
I want **one integration-style test**,  
So that **wiring between config → fetch → merge → write → render** stays intact.

**Acceptance criteria:**

- **Given** mocked HTTP responses for at least one RSS feed, **when** the pipeline runs in test, **then** `results.json` and `index.html` are created in a temp directory and assert basic content (counts, section header, one link).  
- **And** test runs in CI-friendly time (< few seconds).

---

### Story 7.3: Expanded unit tests — merge, render, retries

As a **developer**,  
I want **tests for edge cases**,  
So that **PRD locks don’t regress**.

**Acceptance criteria:**

- **Merge:** item not seen in run does not refresh `last_seen_at`; seen item does.  
- **Render:** `null` date rows last; badge only inside 48h Europe/Rome window.  
- **HTTP:** retry triggers on 503/429 mock sequence; stops after max attempts.  
- **And** test command documented in README.

---

### Story 7.4: Repo hygiene — `.gitignore` & optional CI stub

As a **developer**,  
I want **generated artifacts ignored by default**,  
So that **operators don’t commit noise**.

**Acceptance criteria:**

- **Given** `.gitignore`, **then** it includes `results.json`, `index.html`, `__pycache__`, venv patterns.  
- **And** optional: minimal GitHub Actions workflow **skeleton** (non-blocking for Phase 1) may be added **only if** team wants it—mark as optional in story notes; PRD Phase 2 is automation.

---

## Dependency graph (high level)

```text
E1 → E2 → E3 → E5
        ↘ E4 ↗
E6 can start after E1 (docs) but should be **completed** after E5 for accuracy.
E7 extends E2 (HTTP), E3, E5; finalize after E5.
```

**Recommended execution:** E1 → E2 → E3 → E4 → E5 → **finish E6** → E7.

---

## Definition of Done (Phase 1)

Phase 1 is **done** when:

- PRD §16 acceptance checklist passes against a real `searches.yaml` + `python run.py`.  
- All stories **E1–E7** are **Done** per acceptance criteria.  
- Architect §17 sequencing is reflected in epic order (this document).

---

*End of Epics & Stories — Job Raider Phase 1*
