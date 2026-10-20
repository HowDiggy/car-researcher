# 🚗 Car Research Agent

An AI-powered vehicle research and deal-discovery pipeline that runs daily, scouring the web for comprehensive intelligence on vehicles you're considering buying.

## 📚 Essential Documentation

* **[Operator Guide (`docs/OPERATOR_GUIDE.md`)](file:///Users/paulojauregui/projects/researcher/docs/OPERATOR_GUIDE.md)**: Daily usage, local CLI scans, Discord alerts setup, and troubleshooting.
* **[Agent & LLM Guidelines (`AGENTS.md`)](file:///Users/paulojauregui/projects/researcher/AGENTS.md)**: Developer & AI onboarding guide, architectural invariants, code conventions, and recipes.
* **[Architecture Specification (`docs/architecture.md`)](file:///Users/paulojauregui/projects/researcher/docs/architecture.md)**: Temporal durable execution, single-instance Postgres (TimescaleDB + pgvector), and data model.
* **[Buyer Evaluation Taxonomy (`docs/car-research-agent-data-taxonomy.md`)](file:///Users/paulojauregui/projects/researcher/docs/car-research-agent-data-taxonomy.md)**: Exhaustive 13-category checklist (A through M).

## Project Structure

```
researcher/
├── AGENTS.md                                  # AI & Developer onboarding guide
├── README.md                                  # Project overview & quickstart
├── docker/
│   └── init.sql                               # Postgres init (TimescaleDB, pgvector, pg_trgm)
├── docs/
│   ├── OPERATOR_GUIDE.md                      # Human operator manual & CLI guide
│   ├── car-research-agent-data-taxonomy.md    # Exhaustive 13-category (A–M) buyer taxonomy
│   └── architecture.md                        # Temporal + Postgres/TimescaleDB/pgvector architecture
├── src/
│   ├── config/
│   │   └── settings.py                        # Pydantic Settings (Bay Area 94103, 60mi, $20k-$60k, 14 EVs)
│   ├── models/
│   │   └── domain.py                          # Clean domain dataclasses (listings, recalls, deal scores)
│   ├── db/
│   │   ├── engine.py                          # Async SQLAlchemy 2.0 session factory
│   │   └── models.py                          # ORM tables + TimescaleDB price snapshots
│   ├── activities/
│   │   ├── gov_apis.py                        # NHTSA vPIC VIN decoder, Recalls, Complaints, EPA MPGe
│   │   ├── scoring.py                         # Multi-factor DealScorer (luxury curves, DOM leverage)
│   │   ├── notifications.py                   # Rich markdown dossier formatting & Discord alerts
│   │   ├── persistence.py                     # Database persistence activity for listings & snapshots
│   │   └── scrapers/
│   │       ├── base.py                        # BaseListingScraper with randomized desktop UAs & jitter
│   │       ├── carscom.py                     # Cars.com scraper (JSON-LD Schema.org, Next.js, DOM)
│   │       ├── cargurus.py                    # CarGurus scraper (Playwright network response interception)
│   │       └── aggregator.py                  # MarketplaceAggregator (concurrent scraping, VIN dedup)
│   ├── workflows/
│   │   ├── temporal_compat.py                 # Lightweight compatibility layer for local and test runs
│   │   ├── model_profiler.py                  # ModelProfilerWorkflow (recalls, complaints, EPA specs)
│   │   └── daily_pipeline.py                  # DailyCarResearchPipelineWorkflow (daily surveillance & scoring)
│   └── runner.py                              # Unified CLI & Temporal worker daemon
├── tests/
│   ├── test_domain_unittest.py                # Domain models, DealScorer, Gov API mock tests
│   ├── test_scrapers_unittest.py              # Cars.com, CarGurus, Aggregator VIN dedup tests
│   └── test_daily_pipeline_unittest.py        # Workflow signals, queries, mock execution tests
├── docker-compose.yml                         # TimescaleDB-HA + Temporal Server & Web UI
├── pyproject.toml
└── .env.example / .env
```

## Target Vehicles Scope (Bay Area 60-mile Radius)

The pipeline is pre-configured for **14 electric vehicles** across two distinct value segments:

1. **Mainstream Bang-For-Buck ($20k–$45k Used / $35k–$55k New):**
   * Hyundai Ioniq 5 & 6, Kia EV6 (800V ultra-fast charging, steep depreciation discount)
   * Tesla Model Y & Model 3 (Top value retention, Supercharger network, OTA updates)
   * Ford Mustang Mach-E, Chevrolet Bolt EUV
2. **Upmarket & Luxury EV Depreciation Bargains ($30k–$60k Used):**
   * Mercedes-Benz EQS (Originally $104k–$135k, trading for $45k–$60k — 55-60%+ drop!)
   * Mercedes-Benz EQE (Originally $75k–$95k, trading for $35k–$48k)
   * Cadillac Lyriq (Originally $60k–$80k, trading for $32k–$45k with Super Cruise)
   * BMW i4 (Originally $52k–$75k, trading for $30k–$44k with 4-Series Gran Coupe handling)
   * Genesis GV60, Polestar 2, Audi Q4 e-tron

## Quickstart & Usage

### 1. Run Unit Tests (100% Passing)

```bash
python3 -m unittest discover tests -p "*unittest.py"
```

### 2. Run Single Pipeline Scan (Local CLI)

```bash
# Scan a specific luxury bargain model in Bay Area:
python3 src/runner.py --make "Mercedes-Benz" --model "EQS" --radius 60

# Scan all 14 target models across Cars.com and CarGurus:
python3 src/runner.py --run-once
```

### 3. Run Full Distributed Temporal Stack (Docker)

```bash
# Start TimescaleDB + Temporal Server & Web UI
docker-compose up -d

# Start the Python Temporal Worker
python3 src/runner.py --start-worker
```

Open Temporal UI at `http://localhost:8080` to observe workflows and scheduled cron runs.
