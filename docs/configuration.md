# Configuration (`searches.yaml`)

Job Raider reads a single YAML file (default `./searches.yaml`, or a path passed to `python run.py`). Parsing uses **`yaml.safe_load` only** (no arbitrary object construction).

**Fail-fast (before any HTTP):** If the file is missing, syntactically invalid, or breaks the rules below, the program prints a message to **stderr** and exits with a **non-zero** status. No adapters run and no `requests` traffic is started for sources.

**Canonical reference:** `_bmad-output/planning-artifacts/architecture-job-raider-phase1.md` §5–6.

---

## Top-level keys

| Key | Required | Description |
|-----|----------|-------------|
| `searches` | **Yes** | Non-empty list of search blocks. |
| `version` | No | Must be **`1`** if present. Any other integer → error with supported version hint. |
| `defaults` | No | Optional global HTTP tuning (see below). |

Any other top-level key → error (`unknown top-level keys`).

---

## `defaults` (optional)

| Field | Type | Effect |
|-------|------|--------|
| `request_timeout_seconds` | int | Connect and read timeout for each HTTP request (seconds). |
| `polite_delay_ms` | int | Base delay between requests (milliseconds). The client uses jitter; if set, the range is **`[value, value * 1.5]`** ms. Values below **1000** ms are raised to **1000** ms as the floor. |

Omitted fields use built-in defaults (see `job_raider.http_client`).

---

## `searches[]` — each search

| Field | Required | Description |
|-------|----------|-------------|
| `id` | **Yes** | Stable identifier (non-empty string). Recommended: `[a-z0-9_]+`. |
| `name` | **Yes** | Human-readable title for the dashboard and JSON. |
| `keywords` | **Yes** | Non-empty list of non-empty strings. |
| `sources` | **Yes** | Non-empty list of source blocks. |
| `region` | No | Optional region hint (best-effort; see **Region** below). |
| `max_age_days` | No | Positive integer. When set, drops items with a non-null `published_at` strictly older than this many days versus **now** in **Europe/Rome** (after keyword matching, before normalize). Items with `published_at: null` are **not** dropped by this rule. |
| `require_keywords` | No | List of non-empty strings, or omit / `null`. When **non-empty**, an item must match **at least one** of these phrases (same substring rules as `keywords`) **in addition to** passing the main `keywords` OR filter. Use for “job signal” tokens (e.g. `bando`, `selezione`, `tutor`). |
| `exclude_keywords` | No | List of non-empty strings, or omit / `null`. If **any** phrase appears in title or summary (case-insensitive substring), the item is **dropped**, even if it matched `keywords` and `require_keywords`. Evaluated **after** `require_keywords`. |

Unknown keys under a search → error.

---

## Keyword matching (OR)

After fetch, filters apply in this order:

1. **`keywords` (required)** — item is kept only if **at least one** keyword matches:
   - Case-insensitive **substring** match against **title**.
   - If the adapter provided a **summary**, the same against **summary**.
   - There is no implicit AND between `keywords`.

2. **`require_keywords` (optional)** — if the list is non-empty, the item must also match **at least one** required phrase (same substring rules). Omitted, `null`, or `[]` skips this step.

3. **`exclude_keywords` (optional)** — if **any** listed phrase appears in title or summary, the item is removed. Omitted, `null`, or `[]` skips this step.

4. **`max_age_days`** — when set, surviving rows are filtered by publication age (see table above); `null` dates always pass this step.

### Example (narrow PNRR / bandi)

```yaml
keywords:
  - PNRR
  - orientamento
require_keywords:
  - selezione
  - avviso
  - bando
  - esperto
  - tutor
exclude_keywords:
  - iscrizioni
  - inaugurazione
  - consiglio di istituto
```

---

## Region (best-effort)

- Each adapter declares whether it supports **native** region filtering (`supports_native_region` in code).
- Built-in adapters **`rss`**, **`html_selectors`**, and **`playwright`** do **not** use `region` in the HTTP request.
- When `region` is set and the adapter does not support native region, the **region string** is appended to the **effective keyword list** for filtering (unless it duplicates an existing keyword, case-insensitive), so it can still influence which rows match.

This is **heuristic**, not a geographic guarantee.

---

## `sources[]` — each source

Every source must include:

| Field | Description |
|-------|-------------|
| `adapter` | One of the registered adapter names: **`rss`**, **`html_selectors`**, **`playwright`**. Unknown values → error listing **allowed adapters**. |
| `label` | Non-empty string; stored as `source` on each opportunity and shown in the dashboard. |

All other keys are adapter-specific parameters (see below). Unknown keys are **not** rejected—they become part of the adapter `params` dict.

---

## Adapter: `rss`

Fetches the feed URL and parses entries with **feedparser**.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `url` | **Yes** | Feed URL (`http` or `https`). |
| `link_base` | No | If present, non-empty string passed to URL resolution for relative entry links. |

---

## Adapter: `html_selectors`

Fetches a single HTML page and extracts repeating items with **BeautifulSoup** and CSS selectors.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `url` | **Yes** | Listing page URL. |
| `item` | **Yes** | Selector for each repeating row (e.g. `article.job`). |
| `title` | **Yes** | Selector **relative to each** `item` for title text. |
| `link` | **Yes** | Selector **relative to each** `item` for the `href` to the detail page. |
| `date` | No | Optional selector relative to `item` for a publication date (element text, `datetime` attribute, or common `data-*` attributes—see `job_raider.sources.html_selectors`). |
| `link_base` | No | Base URL for resolving relative links (`urllib.parse.urljoin`). |

---

## Adapter: `playwright`

For **JavaScript-rendered** listing pages (common on Italian school `.edu.it` sites — Albo Pretorio, bandi PNRR) where a plain HTTP GET returns empty or incomplete HTML. Uses **headless Chromium** via [Playwright](https://playwright.dev/python/) to load the page, wait for listing rows, then extract items with the **same CSS selector parameters** as `html_selectors`.

**Optional dependency:** If the `playwright` package is not installed, the source is **skipped** (warning logged, zero items) and the rest of the run continues. After `pip install playwright`, run **`playwright install chromium`** once to download the browser binary.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `url` | **Yes** | Listing page URL. |
| `item` | **Yes** | Selector for each repeating row; also used to **wait** until content is present. |
| `title` | **Yes** | Selector **relative to each** `item` for title text. |
| `link` | **Yes** | Selector **relative to each** `item` for the detail-page `href`. |
| `date` | No | Optional selector relative to `item` for publication date (same parsing as `html_selectors`). |
| `link_base` | No | Base URL for resolving relative links. |

### Example (Albo Pretorio — adjust selectors to the target site)

```yaml
searches:
  - id: scuola_albo
    name: "IIS Example — Albo Pretorio"
    keywords:
      - bando
      - selezione
      - PNRR
      - tutor
    require_keywords:
      - avviso
      - bando
      - selezione
    sources:
      - adapter: playwright
        label: "IIS Example Albo"
        url: "https://www.iisexample.edu.it/albo-pretorio/"
        item: "div.albo-row"
        title: "a.titolo"
        link: "a.titolo"
        date: "span.data-pubblicazione"
        link_base: "https://www.iisexample.edu.it"
```

---

## Robots.txt (NFR3)

Before the first HTTP GET to each **origin** (`scheme://host[:port]`), Job Raider loads `robots.txt` using `urllib.robotparser` (`job_raider.robots.RobotsPolicy`).

- **Per-run cache:** one `RobotFileParser` per origin for the lifetime of the process; there is no cross-run disk cache.
- **Disallow:** if your configured URL is not allowed for the tool `User-Agent`, that **source** is skipped and a log line with `error=robots_disallow` is emitted; other sources still run.
- **Fetch failure:** if `robots.txt` cannot be fetched or parsed, a **warning** is logged and the request is **allowed** (fail-open), so broken robots endpoints do not block the whole run.

Robots coverage does not replace site **terms of service** or legal review; operators remain responsible for compliant use.

---

## Run order vs output order

- **Execution:** Searches run in **`searches.yaml` list order**; within each search, sources run in **YAML order**.
- **Persisted `results.json`:** Search blocks are ordered by **`search_id` ascending** (stable diffs). See `docs/results-schema.md`.

---

## Feed discovery (`discover.yaml`, optional helper)

The standalone script **`discover.py`** (repo root) helps validate candidate RSS/Atom URLs before you add them to `searches.yaml`. It is **not** part of the main `run.py` pipeline.

- **Input file (optional):** `discover.yaml` in the current directory is used automatically if it exists; otherwise pass `-f path/to/file.yaml`. The file may define `urls:` (list of strings) and `keywords:` (list of strings).
- **CLI URLs:** Positional arguments are merged with file URLs (order preserved, duplicates removed).
- **Keywords:** `--keywords a,b,c` overrides keywords from the file when set.
- **Behaviour:** For each URL, the tool tries the URL as-is, then (if the path does not already look like a feed) tries `…/feed/`. It checks **robots.txt**, **GET**s the candidate, validates with **feedparser** (same spirit as the RSS adapter), counts items, and counts how many items match your keywords (OR substring match on title/summary, like the main app). **`--json`** prints a machine-readable report on stdout.
- **Playwright probe (`--playwright`, slower):** When RSS is **unavailable** or **empty**, the tool also checks common Italian school listing paths (`/albo-pretorio/`, `/albo/`, `/comunicati/`, `/news/`, `/circolari/`) against **robots.txt**, fetches allowed pages, and tries to **auto-detect** listing CSS selectors. Output adds a **`playwright`** column (or JSON fields) with:
  - **`ok (suggested selectors)`** — robots allow at least one path and a listing pattern was found (includes suggested `item` / `title` / `link` / `date` for a `playwright` adapter block).
  - **`blocked`** — robots disallow all probed listing paths.
  - **`no-match`** — paths are allowed but no known albo/news pattern matched.
  - **`skipped (rss ok)`** — RSS feed already works; Playwright probe skipped.

See `discover.example.yaml` for a minimal template.

---

## Related docs

- **Output JSON:** [`results-schema.md`](./results-schema.md)  
- **Architecture (Phase 1):** [`architecture.md`](./architecture.md)
