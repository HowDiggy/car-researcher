# 🤖 AGENTS.md — AI & Developer Onboarding Guide

> **For LLMs and Future Developers:** Read this document first before making changes to this codebase. It documents architectural invariants, design patterns, testing protocols, and step-by-step recipes for common extensions.

---

## 1. Project Mission & Mental Model

This system is an **autonomous vehicle research and daily market surveillance engine**. It is engineered to mimic an experienced car buyer by operating on two distinct intelligence tiers:

1. **Macro Intelligence (Model-Level):** Gathers historical reliability, official federal recalls (NHTSA), consumer safety complaints (NHTSA VOQ), and EPA energy efficiency/range metrics for specific makes and models.
2. **Micro Surveillance (Listing-Level):** Daily scrapes regional automotive marketplaces (Cars.com, CarGurus), filters within a geographic radius (Bay Area default: 60 miles of ZIP `94103`), deduplicates listings by 17-digit VIN, evaluates price deltas against empirical fair market value regression, and dispatches alerts for anomalous high-value deals (`deal_score >= 85`).

---

## 2. Architectural Invariants (Non-Negotiable Rules)

When adding or modifying code, preserve these five invariants:

### Rule 1: Temporal Workflow Determinism
* **No network I/O, file access, system time checks (`datetime.now()`), or random number generation directly inside Workflow definitions** (`src/workflows/`).
* Workflows must only coordinate and call **Activities** using `workflow.execute_activity(...)`.
* All non-deterministic logic (scraping, API calls, DB writes, random delays) **must reside in Activities** (`src/activities/`).

### Rule 2: Graceful Zero-Dependency Fallback Pattern
The codebase is designed to run in both:
- **Full Production Mode** (Docker, Temporal server, PostgreSQL 16 + TimescaleDB + pgvector, Playwright).
- **Constrained / Sandbox / Local Test Mode** (Standard Python 3.11+ library with zero external pip packages installed).

**Pattern implemented across all modules:**
```python
try:
    from pydantic import BaseModel
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    from dataclasses import dataclass
```
*Never remove these try/except guards.* They allow the entire unit test suite to pass in 0.002 seconds without requiring external C-extensions, network access, or Docker daemons.

### Rule 3: Cross-Platform Deduplication Priority
Vehicles are listed on multiple platforms simultaneously. Deduplication in `src/activities/scrapers/aggregator.py` must follow:
1. **Primary Key:** 17-character VIN. If matching VINs are found, always retain the listing with the **lower price** or more complete metadata.
2. **Secondary Key:** `clean_make:clean_model:year:mileage_bucket:price` (where mileage is grouped into 500-mile buckets).
3. **Geospatial Constraint:** Drop any listing where `distance_miles > radius_miles`.

### Rule 4: Data Flow & State Hygiene
```
Marketplace Scrapers ➔ Raw Dict ➔ VehicleListing (Domain Dataclass)
                                         │
                                         ▼
                             DealScorer.score_listing()
                                         │
                                         ▼
                                  DealScoreResult
                                         │
                   ┌─────────────────────┴─────────────────────┐
                   ▼                                           ▼
       persist_listings_and_scores()           send_daily_deals_notification()
    (PostgreSQL + TimescaleDB snapshot)            (Markdown / Discord Alert)
```

---

## 3. Directory Map & Key Files

```
researcher/
├── AGENTS.md                                  ← (You are here)
├── README.md                                  ← High-level project overview
├── pyproject.toml                             ← Dependencies (Temporal, SQLAlchemy, Playwright, etc.)
├── docker-compose.yml                         ← TimescaleDB-HA + Temporal Server & Web UI
├── docker/
│   └── init.sql                               ← Database extensions init (timescaledb, vector, pg_trgm)
├── docs/
│   ├── OPERATOR_GUIDE.md                      ← Handbook for human operators running the system
│   ├── architecture.md                        ← Full systems architecture specification
│   └── car-research-agent-data-taxonomy.md    ← Exhaustive 13-category buyer evaluation taxonomy
├── src/
│   ├── runner.py                              ← CLI entrypoint, Temporal worker, & Dashboard launcher
│   ├── config/
│   │   └── settings.py                        # Pydantic Settings with dataclass fallback
│   ├── models/
│   │   └── domain.py                          # Temporal-compatible domain dataclasses
│   ├── db/
│   │   ├── engine.py                          # Async SQLAlchemy engine & session factory
│   │   └── models.py                          # Relational + TimescaleDB ORM schemas
│   ├── dashboard/
│   │   ├── app.py                             # Async HTTP/ASGI Web Dashboard server (port 8000)
│   │   ├── queries.py                         # Lateral join queries, triage toggles, & exports
│   │   └── templates.py                       # Tailwind CSS + HTMX UI components & modals
│   ├── activities/
│   │   ├── gov_apis.py                        # NHTSA vPIC, Recalls, Complaints, EPA client
│   │   ├── scoring.py                         # Multi-factor DealScorer & luxury retention curves
│   │   ├── persistence.py                     # PostgreSQL + TimescaleDB persistence activity
│   │   ├── notifications.py                   # Markdown report formatter & Discord dispatcher
│   │   └── scrapers/
│   │       ├── base.py                        # BaseListingScraper (stealth UAs, jitter)
│   │       ├── carscom.py                     # Cars.com scraper (JSON-LD Schema.org + Next.js)
│   │       ├── cargurus.py                    # CarGurus scraper (Playwright XHR interception)
│   │       └── aggregator.py                  # MarketplaceAggregator (concurrency + VIN dedup)
│   └── workflows/
│       ├── temporal_compat.py                 # Lightweight mock wrapper for Temporal SDK
│       ├── model_profiler.py                  # ModelProfilerWorkflow (macro research)
│       └── daily_pipeline.py                  # DailyCarResearchPipelineWorkflow (daily surveillance)
└── tests/
    ├── test_domain_unittest.py                # Tests for domain models, scoring math, Gov APIs
    ├── test_scrapers_unittest.py              # Tests for scraper parsers & VIN deduplication
    ├── test_daily_pipeline_unittest.py        # Tests for workflow signals, queries, and execution
    └── test_dashboard_unittest.py             # Tests for Web Dashboard routes, filters, & exports
```

---

## 4. Common Developer & LLM Recipes

### Recipe A: Adding a New Vehicle Model to the Watchlist
To add a new vehicle model to the surveillance schedule, edit `src/config/settings.py` (and `.env.example` / `.env`):

```python
# In src/config/settings.py under DEFAULT_TARGET_MODELS:
{"make": "Porsche", "model": "Taycan", "min_year": 2021}
```

If it is a luxury or performance vehicle with an original MSRP above \$55,000, register its estimated base MSRP (and optional trim-specific overrides) in `src/activities/scoring.py`:

```python
# In src/activities/scoring.py:
MODEL_BASE_MSRP_LOOKUP["porsche:taycan"] = 90000
TRIM_MSRP_OVERRIDES.append(("porsche", ["taycan", "turbo"], 160000))
```

### Recipe B: Adding a New Marketplace Scraper
1. Create `src/activities/scrapers/<platform_name>.py`.
2. Inherit from `BaseListingScraper` (`src/activities/scrapers/base.py`).
3. Implement `scrape_listings(...) -> List[VehicleListing]`.
4. Register the new scraper instance inside `MarketplaceAggregator.__init__` in `src/activities/scrapers/aggregator.py`:
   ```python
   self.scrapers = [
       CarsComScraper(headless=headless, proxy_url=proxy_url),
       CarGurusScraper(headless=headless, proxy_url=proxy_url),
       NewPlatformScraper(headless=headless, proxy_url=proxy_url),
   ]
   ```
5. Add unit tests for the scraper's parser in `tests/test_scrapers_unittest.py`.

### Recipe C: Modifying the Deal Scoring Algorithm
The scoring math lives in `src/activities/scoring.py`. The formula calculates:
$$\text{Deal Score} = 0.50 \cdot S_{\text{price}} + 0.25 \cdot S_{\text{history}} + 0.15 \cdot S_{\text{leverage}} + 0.10 \cdot S_{\text{proximity}}$$

- **Price Score:** Linear penalty/bonus based on percentage delta from calculated fair market value.
- **History Score:** 100 base; -50 for salvage/rebuilt title, -20 per accident, -15 for 3+ owners.
- **Leverage Score:** Rewards days on market (DOM > 60 days gets 95 pts due to negotiation room).
- **Proximity Score:** 100 pts for $\le 20\text{ miles}$, scaling down to 70 pts at 60 miles.

---

## 5. Testing & Verification

Always run the full unit test suite after making changes:

```bash
python3 -m unittest discover tests -p "*unittest.py"
```

**Expected output:**
```
Ran 24 tests in 0.012s
OK
```

All 24 tests must pass with zero external dependencies and zero network access.
