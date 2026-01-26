# Hospital Capacity Forecasting (Day 21 scaffold)

Day 21 delivers an ingestion + contracts foundation for a hospital-operations forecasting product:
we snapshot **HHS/HealthData.gov hospital capacity** datasets, load them into **DuckDB** (bronze/silver),
and register a **forecasting contract** that later days will enforce.

Data sources used here are the public HealthData.gov “Reported Patient Impact and Hospital Capacity” datasets.
Note: HHS indicates these specific COVID-era hospital reporting datasets stop being updated after **May 3, 2024**.
You can still use them as a complete historical time series for building the forecasting + alerting pipeline.

## Quickstart

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt

# Day 21: download + ingest (state required; facility optional because it's large)
python -m hospcap.day21 run --db db/hospcap.duckdb --data-dir data --datasets state facility
```

If you want a fast dev run first:

```bash
python -m hospcap.day21 run --db db/hospcap.duckdb --data-dir data --datasets state --max-mb 250
```

## What you get

- `data/raw/...` immutable snapshots (CSV + manifest with SHA256)
- DuckDB:
  - `meta.runs`, `meta.files`, `meta.schemas`
  - `bronze.hhs_state_timeseries_raw`, `bronze.hhs_facility_raw`
  - `silver.hhs_state_timeseries`, `silver.hhs_facility_weekly`
  - `meta.forecast_contracts` (stores `contracts/forecasting_contract_v1.yml`)

## Next days

Day 22–30 will build EDA checks, feature engineering, backtesting, probabilistic forecasts, and a decision/alerting layer on top of the silver tables.
