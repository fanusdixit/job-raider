---
stepsCompleted:
  - executive-summary
  - vision-and-goals
  - success-criteria
  - user-context
  - scope-phasing
  - functional-requirements
  - non-functional-requirements
inputDocuments:
  - User-provided project brief (Job Raider)
workflowType: prd
status: phase-1-locked
phase1LockedDate: 2026-03-19
---

# Product Requirements Document — Job Raider

**Author:** Stefanoguida.nearform  
**Date:** 2026-03-19  
**Version:** 1.0 — **Phase 1 locked**

---

## 1. Executive summary

**Job Raider** is a **local, config-driven Python tool** that aggregates **Italian public-sector, third-sector, and professional job/tender signals** from multiple web sources, persists them as **flat JSON**, and renders a **static HTML dashboard** for offline browsing—**no server, no database, no auth** in Phase 1.

The product’s differentiator is **operational flexibility**: new monitoring “searches” are added by editing **`searches.yaml`** only—**no code changes**—so the same scraper engine supports evolving hiring and tender landscapes (PNRR roles, regional PA competitions, non-profit listings, communications roles, etc.).

### 1.1 Phase 1 locked decisions (normative)

The following are **binding** for Phase 1 implementation and acceptance:

| Topic | Decision |
|-------|----------|
| **Keyword matching** | **OR logic**: a result is included if it matches **any** configured keyword (substring or adapter-defined match—see `docs/`). |
| **“New” badge timezone** | **Always `Europe/Rome`** for interpreting dates and computing the **48-hour** window vs run time. |
| **Missing dates** | Store **`null`** in JSON for unknown publish/listing date; **do not** show the “new” badge; **sort these items to the bottom** within their search section (stable tie-breaker documented, e.g. title or URL). |
| **Stale retention** | Keep opportunities in **`results.json` for 30 days** since **`last_seen_at`** (updated on every run where the item still appears in fetched results). If an item **does not appear** for **30 consecutive days**, **drop** it on the next JSON write. |
| **Invalid `searches.yaml`** | **Fail fast**: clear, human-readable error; **no HTTP/scraper work** runs until config is valid. |
| **Region filter** | **Best-effort**: use **native** source filtering when the adapter supports it; otherwise append the region (as text) to the **search query / keyword set** used for that source so it still influences matching/fetch where applicable. |

---

## 2. Problem statement

People tracking fragmented Italian opportunity sources must repeatedly visit many sites, RSS feeds, and portals. There is no single, **private**, **repeatable** way to run a batch of tailored queries and review **what changed** in one place—especially across **mixed source types** (job boards, institutional sites, official gazettes).

---

## 3. Product vision & goals

### 3.1 Vision

A dependable **personal radar** for Italian opportunities: define what matters in YAML, run one command, get an updated local dashboard grouped by intent (“search”), with clear provenance and recency.

### 3.2 Goals (Phase 1)

| Goal | Description |
|------|-------------|
| **G1** | Run **`python run.py`** to refresh data and regenerate **`index.html`**. |
| **G2** | Support **multiple independent searches** defined in **`searches.yaml`** (name, keywords, sources, optional region filter). |
| **G3** | Persist normalized results in **`results.json`** (flat file). |
| **G4** | Present results in **`index.html`**: grouped by search, each item shows **title, source, date, link**, with a **“new” badge** for items from the **last 48 hours** in **`Europe/Rome`**. |
| **G5** | Use **requests**, **BeautifulSoup4**, **feedparser**, **PyYAML** as the core library stack. |

### 3.3 Non-goals (explicit — Phase 1)

- Authentication / multi-user access  
- Email or push notifications  
- SQL or other databases  
- LinkedIn or other sources that imply login, heavy anti-bot, or ToS risk  
- Mobile-first or responsive layout investment (desktop-first minimal UI is acceptable)  
- Hosted runtime (Phase 1 is local only)

---

## 4. Target users & primary job-to-be-done

### 4.1 Primary user

- **Solo professional or small team member** monitoring Italian tenders/jobs across categories they care about (PA, schools/PNRR, third sector, communications).

### 4.2 Job-to-be-done

> “When I run my weekly scan, I want **one place** to see **new and relevant** opportunities across **my** sources and keywords—**without** maintaining custom scripts per site.”

---

## 5. Success criteria (measurable for Phase 1)

| ID | Criterion | How to verify |
|----|-----------|----------------|
| **SC1** | A user can add a **new search** in `searches.yaml` and see a **new section** in `index.html` after `run.py`—**without code edits**. | Manual test with a dummy search name + keywords. |
| **SC2** | Each result row/card exposes **title, source, date, link** when those fields exist at the source. | Spot-check HTML output against raw fetch. |
| **SC3** | Items with a **non-null** publication/listing date within **48h** of run time in **`Europe/Rome`** show a **visible “new”** treatment; **null** dates never get the badge. | Fixture JSON + run metadata timestamp. |
| **SC3b** | Within each search section, items with **null** date sort **after** all dated items. | Inspect `index.html` / JSON ordering. |
| **SC3c** | Records older than **30 days** per retention rule are **removed** from `results.json` on write. | Seed aged records, run, assert absence. |
| **SC6** | **Invalid** `searches.yaml` exits **before** any network requests with a **clear error**. | Malformed YAML / missing required keys. |
| **SC4** | Run completes with **clear logging** (stdout and/or log file—implementation choice) indicating per-search success/failure. | Run with one broken source; observe non-silent failure. |
| **SC5** | `results.json` is **stable enough** to diff in git (deterministic ordering per search, consistent schema). | Two runs with no upstream changes produce identical JSON (or documented acceptable variance). |

---

## 6. Illustrative configuration (not hard-coded product logic)

The brief lists **example** search categories to seed `searches.yaml`; the **product must not hard-code** these names or sources—they are **sample content** for documentation and default starter config only.

Examples called out in the brief:

- PNRR school orientation experts — *InPA, USR Lazio/Campania*  
- PA competitions — *Lazio, Campania, nearby* — *InPA, Gazzetta Ufficiale*  
- Third sector / non-profit — *Vita.it, JobInVolontariato*  
- Communications / editorial — *Indeed Italy, Corriere Comunicazioni*

**Requirement:** The engine treats **source types** and **URLs/endpoints** as **data driven** from config (see §8), not as fixed enums in code—though **per-source adapters** in code are expected where HTML/RSS shapes differ.

---

## 7. User journeys (Phase 1)

### 7.1 Configure searches

1. User copies or edits `searches.yaml`.  
2. User defines one or more searches with **name**, **keywords**, **sources**, optional **region** filter.  
3. User saves file.

### 7.2 Run scraper & view dashboard

1. User runs `python run.py` from project root (or documented working directory).  
2. Tool fetches and parses configured sources per search.  
3. Tool merges new fetch with prior `results.json` according to **deduplication rules** (see FRs).  
4. Tool writes updated `results.json`.  
5. Tool writes `index.html`.  
6. User opens `index.html` in a browser; scans sections; clicks links to original postings.

### 7.3 Recover from partial failure

1. One source times out or returns unexpected HTML.  
2. Run continues for other sources/searches where possible.  
3. User sees **which search/source failed** in logs; dashboard still renders available data.

---

## 8. Configuration requirements (`searches.yaml`)

### 8.1 Purpose

`searches.yaml` is the **authoritative definition** of what to monitor. The scraper **must** read it at **runtime** (each run).

### 8.2 Required concepts (logical schema)

Document the **exact** YAML keys in project docs; PRD-level requirements:

| Field | Required | Description |
|-------|----------|-------------|
| **search name / id** | Yes | Human-readable section title in dashboard; stable id for grouping in JSON. |
| **keywords** | Yes | One or more terms/phrases; matching uses **OR logic** (§1.1): **any** keyword match includes the result. |
| **sources** | Yes | List of source definitions the engine knows how to execute (type + parameters). |
| **region filter** | No | **Best-effort** (§1.1): native filter when supported; else region text is appended to the query/keyword side of the fetch for that source. |

### 8.3 Validation

- **Invalid YAML**, **schema violations**, or **missing required fields** → **fail fast** with a **clear, human-readable error** and **exit before any scraper/HTTP activity**.

### 8.4 Security & hygiene

- Config may contain URLs; **no arbitrary code execution** from YAML.  
- Document that users should not commit secrets; Phase 1 has **no secret management** scope.

---

## 9. Data requirements (`results.json`)

### 9.1 Purpose

Single **flat** JSON file acting as the **system of record** for the last successful materialization of opportunities.

### 9.2 Logical content

- **Metadata**: run timestamp, tool version (recommended), optional notes.  
- **Results grouped by search** (by search id/name).  
- **Each opportunity record** (minimum fields):

| Field | Required | Notes |
|-------|----------|--------|
| `title` | Yes | Display title; fall back policy if missing = implementation detail (must be documented). |
| `source` | Yes | Short label (e.g., site name). |
| `url` | Yes | Canonical link to opportunity. |
| `published_at` (or canonical `date`) | Nullable | Use JSON **`null`** when unknown. **No** “new” badge if null. Badge window uses **`Europe/Rome`** vs run time (§1.1, §10.1). |
| `search_id` / `search_name` | Yes | Traceability to originating search. |
| `last_seen_at` | Yes | ISO 8601 timestamp (with offset or Z); updated whenever this opportunity appears in a successful merge; drives **30-day** pruning (§1.1, §9.4). |

### 9.3 Deduplication & identity

- Define a **dedupe key** (recommendation: **normalized URL**; if URL unstable, hash of title+source+date—document chosen strategy).  
- Re-runs should **not** multiply identical items.

### 9.4 Merge, retention, and orphans

- On each successful write, the system **merges** new fetch results with prior state, **dedupes** per §9.3, **updates** fields (e.g. title/date) when the same identity reappears.  
- **Retention:** any opportunity **not seen for 30 days** (per §1.1 “last seen” or documented alternative) is **dropped** from `results.json`.  
- **Orphans** (disappeared from source): treated per retention—if never seen again, they age out at **30 days** after last seen.

---

## 10. Dashboard requirements (`index.html`)

### 10.1 Functional (static site)

- **Single file** `index.html` (inline or relative assets acceptable if still static and local-open friendly; simplest path: **inline CSS**).  
- **Sections** per **search** from `results.json` / last run output.  
- Each item: **title** (linked), **source**, **date**, **link**.  
- **“New” badge** only when `published_at` is **non-null** and falls within **48 hours** of the run’s generation timestamp, compared in **`Europe/Rome`**.  
- **`null` dates:** **no** “new” badge; in the UI list, sort **to the bottom** of that search section (after all dated items).  
- Sort within section: **descending by date** (newest first) for dated items; **null** dates last; stable secondary sort documented (e.g. title).

### 10.2 UX / visual

- **Clean, minimal** layout; readable typography; sufficient contrast.  
- **Desktop-first**; mobile layout **out of scope** for Phase 1.  
- No dependency on external CDNs **optional**—recommend **no network-required assets** so offline viewing works after run.

### 10.3 Performance expectations (PRD level)

- Handle **thousands** of rows across searches without browser lock-up (e.g., simple pagination or collapsible sections **nice-to-have**; not required for MVP if dataset stays small).

---

## 11. Functional requirements

*Testable capabilities. Wording: **[Actor] can [capability]**.*

### 11.1 Configuration & extensibility

- **FR1:** The operator can define **arbitrary searches** in `searches.yaml` without modifying Python source files.  
- **FR2:** The system can load and parse `searches.yaml` at the start of each run.  
- **FR3:** The operator can assign **keywords** to a search; results are included when **any** keyword matches (**OR** semantics per §1.1).  
- **FR4:** The operator can assign **one or more sources** to each search.  
- **FR5:** The operator can optionally specify a **region filter**; the system applies it **natively** when supported, otherwise **appends** the region to the query/keyword side of the fetch (**best-effort**, §1.1).  
- **FR6:** If `searches.yaml` is invalid or incomplete, the system **aborts before scraping**, prints a **clear error**, and performs **no** HTTP requests.

### 11.2 Fetching & parsing

- **FR7:** The system can retrieve remote content over HTTP for configured sources using `requests`.  
- **FR8:** The system can parse **HTML** listings/pages using `BeautifulSoup4` where applicable.  
- **FR9:** The system can parse **RSS/Atom feeds** using `feedparser` where applicable.  
- **FR10:** The system can execute **multiple searches** in one run and aggregate their outputs.  
- **FR11:** The system can continue processing **remaining searches/sources** when one source fails (**partial success**).

### 11.3 Normalization, storage, and deduplication

- **FR12:** The system can normalize heterogeneous source items into a **common opportunity schema** before writing JSON.  
- **FR13:** The system can **deduplicate** opportunities across repeated runs using a documented identity rule.  
- **FR13b:** The system can set or refresh **`last_seen_at`** whenever a deduped opportunity **appears** in the current run’s fetch/merge results.  
- **FR14:** The system can persist the full result set to **`results.json`**, using **`null`** for unknown publish dates (§1.1).  
- **FR15:** The system can **remove** records absent for **more than 30 days** per §9.4 / §1.1 on each write.  
- **FR15b:** The operator can **delete or reset** `results.json` manually to force a cold start (documented operational procedure).

### 11.4 Dashboard generation

- **FR16:** The system can generate **`index.html`** from the persisted results (same run as scrape, or immediately after JSON write).  
- **FR17:** The viewer can see results **grouped by search name** in the HTML.  
- **FR18:** The viewer can open the **original posting** via the opportunity link.  
- **FR19:** The viewer can visually distinguish **new** opportunities (**non-null** date within **48 hours** in **`Europe/Rome`** vs run time); **null** dates **never** show the badge.  
- **FR19b:** The viewer sees items **without** dates **after** all dated items within the same search section.  
- **FR20:** The dashboard requires **no application server** to view.

### 11.5 Operations & developer experience

- **FR21:** The operator can run **`python run.py`** as the **primary entry point** for Phase 1.  
- **FR22:** The system can emit **per-search and per-source** status (success, empty, error) during a run.  
- **FR23:** The repository includes **documented** steps to create a virtualenv, install dependencies, and run the tool.

---

## 12. Non-functional requirements

### 12.1 Reliability & resilience

- **NFR1:** **Invalid configuration** must abort the run **before** any HTTP (per FR6). A single source failure (HTTP error, timeout, parse mismatch) **must not crash the entire run** for otherwise-valid config (per FR11).  
- **NFR2:** Timeouts and retries should be **bounded** (specific values left to architecture; must exist to avoid hangs).

### 12.2 Legal, ethical, and compliance

- **NFR3:** The scraper **must respect** each target site’s **robots.txt** where feasible and documented.  
- **NFR4:** Default fetch rate must be **conservative** (politeness delay between requests—exact numbers in architecture).  
- **NFR5:** User is responsible for **terms of use** compliance; documentation must **warn** against scraping prohibited sources.

### 12.3 Maintainability

- **NFR6:** Adding a **new source type** should be possible by extending a **small, documented** adapter interface (exact pattern in architecture).  
- **NFR7:** Core configuration schema and JSON output schema **must be documented** in `docs/` for intermediate users (per BMAD project knowledge path).

### 12.4 Security (Phase 1 scope)

- **NFR8:** No credentials stored in repo config for Phase 1.  
- **NFR9:** Generated HTML must **escape** untrusted text fields to mitigate XSS when opening `index.html` (defense-in-depth even for local use).

### 12.5 Performance (local)

- **NFR10:** Typical runs (brief’s initial source count, moderate keywords) should complete in **under a few minutes** on a normal laptop, network permitting—not a hard SLA, but a design target.

---

## 13. Phase 2 (forward-looking, non-binding)

Documented for alignment only; **not part of Phase 1 acceptance**.

- **GitHub Actions** scheduled runs (e.g., daily).  
- Optional publish to **GitHub Pages** or artifact hosting.  
- Possible notifications (email/Slack) **after** stable data pipeline.

---

## 14. Risks & assumptions

| Item | Risk / assumption | Mitigation |
|------|-------------------|------------|
| **R1** | Site HTML changes break parsers | Adapter isolation, tests with fixtures, visible parse errors. |
| **R2** | Rate limits / blocking | Polite delays, user-agent policy, documented proxy option (future). |
| **R3** | Incomplete dates from sources | Store **`null`**, no badge, sort last; document adapter behavior. |
| **R5** | 30-day retention drops wanted old items | Users rely on upstream sites or lengthen retention via future PRD change. |
| **R4** | Indeed / job boards ToS | Prefer RSS/API where allowed; document user responsibility. |
| **A1** | User runs Python **3.11+** locally | State in README. |

---

## 15. Deferred / architecture detail (not locked in PRD)

1. **Source definition format** in YAML: single URL vs templates—left to technical design in `docs/` and architecture.  
2. *(Resolved in §1.1)* **30-day clock** uses **`last_seen_at`** only.  
3. **Initial `searches.yaml`**: ship **examples only** vs fully working starter set—implementation/docs decision (legal + feasibility per source).

---

## 16. Acceptance checklist (Phase 1)

- [ ] `searches.yaml` drives all searches; adding a search needs **no code change**.  
- [ ] **Bad YAML / invalid schema** → **fail fast**, **no** HTTP, **clear** error (SC6, FR6).  
- [ ] **Keywords** use **OR** matching (§1.1, FR3).  
- [ ] **Region** = native when possible, else **appended to query** (§1.1, FR5).  
- [ ] `python run.py` updates **`results.json`** and **`index.html`**.  
- [ ] **30-day** pruning of stale records (SC3c, FR15).  
- [ ] **`null`** dates stored when unknown; **no** new badge; **sorted last** per section (SC3b, FR19b).  
- [ ] **“New”** badge uses **`Europe/Rome`** and **48h** window (SC3).  
- [ ] Dashboard is **static** and usable via `file://` or simple open-in-browser.  
- [ ] Dependencies limited to **requests**, **beautifulsoup4**, **feedparser**, **PyYAML** (+ stdlib) unless explicitly amended in a future PRD revision.  
- [ ] README + `docs/` cover config schema, JSON schema, retention, timezone, and operational troubleshooting.

---

## 17. Traceability note

This PRD is the **capability contract** for UX (dashboard), architecture (adapters, pipeline), and downstream epics/stories. Features not listed here should be treated as **out of scope** until the PRD is updated.

---

*End of PRD v1.0 — Phase 1 locked*
