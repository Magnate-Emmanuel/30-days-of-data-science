# Day 11 — No-Show Project Setup (Bronze → Silver → Gold + Contract)

## Goal for today
Set up the “No-Show Risk + SMS Causal Effect + Targeting Policy” project in a way that is reusable for the next 10 days:
- Ingest raw data into DuckDB (bronze)
- Standardize and clean (silver)
- Create a canonical modeling/policy base table (gold)
- Create a feature contract JSON (what the model expects at scoring time)
- Create a smoke input CSV template (deployment mindset)
- Run data-quality checks and fix the important issues immediately

---

## Dataset
Medical Appointment No Shows dataset.

Raw file location:
- `Day-11/data/raw/appointments.csv`

Raw columns detected (bronze):
- `PatientId, AppointmentID, Gender, ScheduledDay, AppointmentDay, Age, Neighbourhood, Scholarship, Hipertension, Diabetes, Alcoholism, Handcap, SMS_received, No-show, ingest_ts`

Row count (raw):
- `110,527`

---

## Warehouse (DuckDB)
DuckDB file location:
- `Day-11/data/warehouse/day11_noshow.duckdb`

Tables created:
- `bronze_appointments`  (raw as-is, all varchar + ingest timestamp)
- `silver_appointments`  (cleaned + standardized + derived fields)
- `gold_appointments_base` (canonical base table for modeling/policy)

---

## Standardization decisions (Silver)
1) **Column name standardization**
- Lowercase + underscores (e.g., `PatientId` → `patientid`, `No-show` → `no_show`)

2) **Canonical renaming**
- `patientid` → `person_id`
- `appointmentid` → `appointment_id`

3) **Datetime parsing and the lead-time fix (critical)**
Problem discovered:
- Many rows looked like “appointment < scheduled” when comparing timestamps.
Cause:
- `ScheduledDay` includes time-of-day, while `AppointmentDay` often behaves like a date (midnight).
Fix:
- Use calendar dates (DATE) for time logic:
  - `scheduled_ts`, `appointment_ts` as timestamps
  - `scheduled_date`, `appointment_date` as dates
  - `lead_time_days = appointment_date - scheduled_date` (days)

4) **Bad ages**
- Ages outside `[0, 110]` are invalid.
- Found and removed: `6` rows.

5) **True DATE-level inversions**
- After DATE logic, only `5` rows still had negative `lead_time_days`.
- These are true inconsistencies (not time-of-day artifacts), so they were removed.

6) **Outcome label**
- Created `label` where:
  - `label = 1` means **No-show**
  - `label = 0` means **Show**
- Source: `no_show == "Yes"` → no-show.

7) **Treatment indicator**
- `sms_received` kept as the intervention indicator (for causal and policy modeling).

---

## Gold base table (canonical)
Table:
- `gold_appointments_base`

Contains the fields needed for the next steps (EDA, features, splits, modeling, causal estimation):
- IDs: `appointment_id`, `person_id`
- Time: `scheduled_ts`, `appointment_ts`, `scheduled_date`, `appointment_date`, `lead_time_days`
- Patient/appointment covariates: `age`, `gender`, `neighbourhood`, `scholarship`, `hipertension`, `diabetes`, `alcoholism`, `handcap`
- Treatment: `sms_received`
- Outcome: `label`

---

## Data quality checks (final)
Final counts after cleaning:
- `bronze: 110527`
- `silver: 110516`
- `gold: 110516`

Checks:
- Duplicates by `appointment_id`: `0`
- Label nulls: `0`
- Age out of range: `0` (after removing 6 invalid rows)
- DATE-level inversions: `0` (after removing 5 inconsistent rows)

No-show prevalence (after cleaning):
- approximately `0.2019`

---

## Artifacts written today

### 1) Feature contract JSON
This defines what columns must be present at scoring time (and how they’re treated).

Path:
- `Day-11/artifacts/noshow_feature_contract.json`

Contents:
- `id_cols`: `["appointment_id", "person_id"]`
- `label_col`: `"label"`
- `treatment_col`: `"sms_received"`
- `feature_cols`:
  - `age, gender, neighbourhood, scholarship, hipertension, diabetes, alcoholism, handcap, lead_time_days`
- `numeric_cols`: `["age", "lead_time_days"]`
- `categorical_cols`: `["gender", "neighbourhood"]`
- `binary_cols`: `["scholarship","hipertension","diabetes","alcoholism","handcap"]`

Important rule:
- `sms_received` is **not** a risk-model feature. It is a treatment/policy variable.

### 2) Smoke input template CSV
A tiny example input in “deployment format” (what a scoring script would accept).

Path:
- `Day-11/data/input_example.csv`

Columns included:
- `appointment_id, person_id, age, gender, neighbourhood, scholarship, hipertension, diabetes, alcoholism, handcap, lead_time_days`

---

## What Day 11 accomplished
By the end of Day 11 we have:
- A clean, reproducible DuckDB warehouse (bronze/silver/gold)
- Correct time logic (`lead_time_days`) that will not cause leakage or date bugs
- A contract that defines scoring-time expectations (inputs/feature types)
- A smoke input file so we keep “deployment thinking” from day one

Next: Day 12 will do expert EDA and data dictionary work, and decide exactly what is allowed at scoring time vs what would be leakage.
