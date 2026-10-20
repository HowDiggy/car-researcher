# 🚗 Car Research Agent

An AI-powered vehicle research and deal-discovery pipeline that runs daily, scouring the web for comprehensive intelligence on vehicles you're considering buying.

## Project Structure

```
researcher/
├── docs/                          # Design documents & taxonomy
│   └── car-research-agent-data-taxonomy.md   # Exhaustive data taxonomy (13 categories, A–M)
├── .gitignore
└── README.md
```

## Overview

This system operates on two intelligence layers:

1. **Macro Layer (Model-Level Intelligence)** — Weekly deep-dives per make/model/year: specs, reliability, recalls, safety, sentiment, TCO, legal exposure, software risks, market timing signals.
2. **Micro Layer (Listing-Level Surveillance)** — Daily scraping of active market listings, price tracking, deal scoring, and push alerts for below-market opportunities.

## Status

🟡 **Design Phase** — Defining data taxonomy and system architecture.
