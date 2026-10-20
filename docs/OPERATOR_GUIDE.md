# 🚗 Car Researcher Operator Guide

Welcome to the operator manual for your AI-powered Car Research and Daily Surveillance Pipeline. This guide covers daily operations, configuration adjustments, CLI commands, and deployment instructions.

---

## 1. Quick Cheat-Sheet (Most Common Commands)

| Goal | Command |
| :--- | :--- |
| **Run all unit tests** | `python3 -m unittest discover tests -p "*unittest.py"` |
| **Run an instant scan for all 14 EV models** | `python3 src/runner.py --run-once` |
| **Scan a specific car model** | `python3 src/runner.py --make "Mercedes-Benz" --model "EQS" --radius 60` |
| **Change search radius on the fly** | `python3 src/runner.py --make "BMW" --model "i4" --radius 40` |
| **Start full Docker stack** *(Postgres + Temporal + Worker + Dashboard)* | `docker compose up -d` |
| **Open Web Dashboard (Deals, History, NHTSA/EPA, CSV Export)** | Open `http://localhost:8000` in your browser |
| **View Temporal Web UI** | Open `http://localhost:8080` in your browser |
| **Start Web Dashboard locally (outside Docker)** | `python3 src/runner.py --start-dashboard --port 8000` |
| **Start Temporal background worker** | `python3 src/runner.py --start-worker` |

---

## 2. Configuration & Customization

All primary operational parameters live in your local `.env` file (copied from `.env.example`).

### 2.1 Adjusting Location & Budget
If you want to tighten or expand your geographic search area or budget:

```bash
# In .env:
SEARCH_ZIP_CODE="94103"      # Bay Area center anchor
SEARCH_RADIUS_MILES=60       # Search radius in miles
SEARCH_MIN_PRICE=20000       # Floor price in USD
SEARCH_MAX_PRICE=60000       # Ceiling price in USD
```

### 2.2 Customizing Target Vehicles
The pipeline currently tracks **14 high-value electric vehicles** pre-configured in `.env`:

```json
SEARCH_TARGET_MODELS='[
  {"make": "Hyundai", "model": "Ioniq 5", "min_year": 2022},
  {"make": "Hyundai", "model": "Ioniq 6", "min_year": 2023},
  {"make": "Kia", "model": "EV6", "min_year": 2022},
  {"make": "Tesla", "model": "Model Y", "min_year": 2022},
  {"make": "Tesla", "model": "Model 3", "min_year": 2022},
  {"make": "Ford", "model": "Mustang Mach-E", "min_year": 2022},
  {"make": "Chevrolet", "model": "Bolt EUV", "min_year": 2022, "max_year": 2023},
  {"make": "BMW", "model": "i4", "min_year": 2022},
  {"make": "Mercedes-Benz", "model": "EQS", "min_year": 2022},
  {"make": "Mercedes-Benz", "model": "EQE", "min_year": 2023},
  {"make": "Cadillac", "model": "Lyriq", "min_year": 2023},
  {"make": "Genesis", "model": "GV60", "min_year": 2023},
  {"make": "Polestar", "model": "2", "min_year": 2022},
  {"make": "Audi", "model": "Q4 e-tron", "min_year": 2022}
]'
```

To add or remove models, simply edit this JSON array in your `.env`.

---

## 3. How the Deal Scoring Engine Evaluates Cars

Every discovered vehicle is scored from **0 to 100** by `DealScorer` using the formula:

$$\text{Composite Score} = 0.50 \cdot S_{\text{price}} + 0.25 \cdot S_{\text{history}} + 0.15 \cdot S_{\text{leverage}} + 0.10 \cdot S_{\text{proximity}}$$

### Recommendation Tiers:

| Score | Tier | Meaning | Action |
| :--- | :--- | :--- | :--- |
| **$\ge 85$** | `EXCELLENT_DEAL` | Priced $\ge \$3,000$ below fair market value, clean title, low accident risk | **Instant push alert sent** |
| **$75 - 84$** | `GOOD_VALUE` | Solid market price, good maintenance, fair mileage | Recorded in daily report |
| **$60 - 74$** | `FAIR_MARKET` | Average retail price; minimal negotiation margin | Saved to database |
| **$< 60$** | `OVERPRICED_OR_HIGH_RISK` | Overpriced, salvage/rebuilt title, or multi-accident history | Filtered out of alerts |

### Key Scoring Rules:
1. **Empirical EV Depreciation Curves:** The algorithm models the distinct depreciation cliff of modern EVs. For luxury models (Mercedes EQS, Cadillac Lyriq), it applies a steep 3-year retention curve ($45\%$) off the original six-figure MSRP.
2. **Title Penalties:** Salvage, rebuilt, or lemon-law buyback titles receive an automatic **-50 point penalty**, preventing them from qualifying as an `EXCELLENT_DEAL` regardless of how cheap they appear.
3. **Days on Market (DOM) Leverage:** Vehicles that have sat on dealer lots for $>60$ days receive bonus leverage points ($95/100$) because dealerships face mounting floor-plan carrying costs and are eager to negotiate.

---

## 4. Setting Up Instant Deal Alerts (Discord Webhook)

Getting notifications when a great deal appears takes 30 seconds:

1. In your Discord server, go to **Server Settings ➔ Integrations ➔ Webhooks ➔ New Webhook**.
2. Name it `Car Researcher` and copy the Webhook URL.
3. Paste it into your `.env` file:
   ```bash
   DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_URL_HERE"
   ```
4. Run a test scan:
   ```bash
   python3 src/runner.py --run-once
   ```
   When high-scoring deals are found, a formatted Markdown dossier with direct links, price savings, and proximity will appear in your Discord channel automatically.

---

## 5. Production Deployment (Docker + Temporal)

For automated daily 6:00 AM background runs:

### Step 1: Start Infrastructure Containers
```bash
docker-compose up -d
```
This spins up:
- **TimescaleDB-HA (Postgres 16):** Stores relational tables, `pgvector` embeddings, and time-series `price_snapshots`.
- **Temporal Server (`temporalio/auto-setup`):** The workflow engine managing retries and schedules.
- **Temporal Web UI:** Available at `http://localhost:8080`.

### Step 2: Launch the Worker Process
```bash
python3 src/runner.py --start-worker
```
The worker registers `DailyCarResearchPipelineWorkflow` and `ModelProfilerWorkflow` and listens for scheduled runs or ad-hoc triggers.

---

## 6. Inspecting Price Drop Trends in SQL

Once the pipeline has collected data over several days, you can run queries against TimescaleDB to spot price drops:

```sql
-- Find vehicles with active price drops in the last 7 days
SELECT 
    l.title,
    l.price AS current_price,
    ps.price AS previous_price,
    (ps.price - l.price) AS total_discount,
    l.url
FROM listings l
JOIN price_snapshots ps ON ps.listing_id = l.id
WHERE ps.time < NOW() - INTERVAL '3 days'
  AND (ps.price - l.price) > 1000
ORDER BY total_discount DESC;
```

---

## 7. Troubleshooting & FAQ

* **Q: Do I need a proxy to scrape?**
  * *A:* For light local scans (1–3 models), no proxy is needed. For large daily scans covering all 14 models, residential proxy rotation is recommended to prevent marketplace rate limits. Set `SCRAPER_RESIDENTIAL_PROXY_URL` in `.env`.
* **Q: Can I run this without Docker?**
  * *A:* Yes! Running `python3 src/runner.py --run-once` executes the entire pipeline in standalone mode without requiring Docker or Temporal.
* **Q: How do I know if an EV has heat-pump cabin heating?**
  * *A:* Look at the `specs` column in `vehicle_models` or query `ModelProfilerWorkflow`, which extracts official EPA configurations and options.
