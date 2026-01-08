# Day 12 — Discovery (EDA the expert way) for No-Show + SMS Project

## Goal
Turn the cleaned Day 11 gold table into an expert “project understanding” layer:
- document what fields exist and what is allowed at scoring time
- check missingness and data quality
- understand the outcome (no-show) patterns
- check whether SMS assignment looks non-random (confounding signal)
- write reusable checks/tables that can later become automated tests

---

## Data source
DuckDB (from Day 11):
- `Day-11/data/warehouse/day11_noshow.duckdb`
- table: `gold_appointments_base`

Rows (gold): 110,516

---

## Scoring-time mindset (leakage hygiene)
We assume this system is used at scheduling time to decide whether to send an SMS reminder.
Therefore:
- **Features** must be known at scheduling time (age, gender, neighborhood, lead time, etc.).
- **Treatment** is `sms_received` (policy lever), not a risk-model feature.
- **Outcome** is `label` (1 = no-show, 0 = show), never used as a feature.

Allowed feature set (v0):
- `age, gender, neighbourhood, scholarship, hipertension, diabetes, alcoholism, handcap, lead_time_days`

---

## Missingness
Result: **no missingness** in the selected fields (all missing_count = 0, missing_rate = 0).

This is unusual for healthcare-style datasets, but it simplifies modeling:
- no need for imputation in baseline models
- no “missingness indicator” feature needed (for now)

Missingness-outcome shift analysis:
- not applicable (no missing values)

---

## Data-quality checks (pass/fail)
All checks passed on the cleaned gold table:

```json
{
  "rows_gold": 110516,
  "dup_appointment_id": 0,
  "label_nulls": 0,
  "sms_nulls": 0,
  "lead_negative": 0,
  "age_out_of_range": 0
}
