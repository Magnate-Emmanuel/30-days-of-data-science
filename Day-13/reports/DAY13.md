# Day 13 — Feature Engineering (Time Logic Matters)
Project: No-Show Risk + Causal Effect of SMS + Targeting Policy

## Goal
Build a reproducible, leakage-aware feature table for modeling:
- predictive no-show risk (calibrated)
- later causal work (propensity + AIPW)
- later decision layer (targeting under budget)

Deliverable: DuckDB table `gold_appointments_features_v1` + a v1 feature contract JSON.

---

## Inputs
DuckDB (Day 11 warehouse):
- `Day-11/data/warehouse/day11_noshow.duckdb`
- base table: `gold_appointments_base`

---

## Output table (Gold v1)
Created table:
- `gold_appointments_features_v1`

### Row counts + prevalence checks
- rows: **110,516**
- no-show prevalence: **0.2018802707**
- duplicate appointment_id: **0**

This confirms the feature build did not change the population and did not introduce duplication.

---

## What features we engineered (v1)

### 1) Time / calendar features
From appointment/scheduled dates (and scheduling timestamp hour where available):
- `appt_dow`, `appt_month`
- `sched_dow`, `sched_month`
- `sched_hour` (nullable if no timestamp time component exists)

Why: no-shows often vary by weekday/season/time-of-day.

### 2) Lead time transforms
From `lead_time_days`:
- `lead_time_clipped` (clipped to a safe range; protects models from extreme values)
- `lead_time_log1p` (log(1 + max(0, lead_time_days)) for smoother nonlinearity)
- `lead_time_bin` (categorical bucket such as same_day, 1_2, 3_7, 8_14, …)

Why: lead time was the strongest pattern in Day 12; these versions let both linear and tree models capture it well.

### 3) Neighborhood handling (high-cardinality)
We added:
- `nbhd_n` = neighborhood frequency (count of rows in that neighborhood)

We also created a grouping concept (`neighbourhood_grp` inside the SQL), which is a safe step toward avoiding overfitting on tiny neighborhoods.

Why: neighborhood is informative but high-cardinality. We want signal without memorizing identities.

### 4) Patient history feature (no look-ahead)
We created:
- `prior_appt_count` = number of prior appointments for this person before the current appointment date.

Sanity:
- min_prior = 0
- max_prior = 87
- mean_prior ≈ 1.2702

Why: history is predictive, but must be computed strictly using prior events to avoid time leakage.

---

## Feature contract v1 (for modeling + future scoring)
Wrote:
- `Day-13/artifacts/noshow_feature_contract_v1.json`

Contents:
- id columns: `appointment_id`, `person_id`
- label: `label`
- treatment: `sms_received`
- feature columns (19 total): age, gender, neighbourhood, comorbidity flags, lead-time transforms, calendar fields, nbhd_n, prior_appt_count
- numeric vs categorical split:
  - numeric: age, lead-time numeric transforms, calendar integers, nbhd_n, prior_appt_count, plus binary flags
  - categorical: gender, neighbourhood, lead_time_bin

---

## Smoke input template
Created a `input_example_v1.csv` template for keeping “deployment thinking” alive.
Note: in a real production scoring pipeline, some engineered fields should be computed from raw scheduling timestamps rather than required in the input. We will improve this during deployment packaging.

---

## Next (Day 14)
We will create:
- leakage-safe splits (patient-level + optional time split)
- split tables stored in DuckDB
- guardrails to ensure:
  - no patient overlap across train/valid/test
  - no use of post-outcome features
  - consistent feature contract across steps
