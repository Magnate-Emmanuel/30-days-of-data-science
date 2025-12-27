# Day 1 — Setup + First End-to-End Pipeline (Bronze → Silver → Gold)

## What I did today
Today I set up a simple, local “data warehouse” using DuckDB and built my first end-to-end data pipeline using the Diabetes 130-US hospitals readmission dataset. The goal is to practice the same workflow that appears in modern cloud data systems: ingest raw data, clean it in a controlled way, create an analysis-ready table, and verify data quality before modeling.

## Dataset
I used the UCI diabetes readmission dataset (`diabetic_data.csv`). Each row represents a hospital encounter. The dataset includes an outcome variable `readmitted` that indicates whether the patient was readmitted and how soon.

## The business problem (in plain language)
Healthcare teams often have limited capacity to do outreach (calls, follow-ups, care coordination). A practical decision-support system should help decide who to contact first. In this learning project, I treat “readmitted within 30 days” as the high-risk outcome I want to predict so that, in a real setting, the system could prioritize outreach to reduce early readmissions.

## What “Bronze / Silver / Gold” means (explain like I’m a beginner)
- **Bronze**: the raw data, loaded as-is. I avoid changing meaning here. The goal is to preserve what came from the source.
- **Silver**: cleaned and standardized data. I handle obvious missing markers (like `?`), and get the data into a more consistent format.
- **Gold**: analysis-ready table. This is where the table is shaped for modeling and decision making: clear ID fields, a time index, and a label (outcome).

## What tables I created
1. **bronze_diabetes**
   - Raw CSV loaded into DuckDB
   - I added `ingest_ts` to record when I loaded the data
   - Row count: 101,766

2. **silver_diabetes**
   - I converted `?` values into proper NULL values across columns
   - Row count: 101,766

3. **silver_diabetes_typed**
   - I selected key columns and cast them into numeric types
   - I created a binary label:
     - `label = 1` if `readmitted == '<30'`
     - `label = 0` otherwise

4. **gold_diabetes_base**
   - Final modeling table with one row per encounter
   - Columns: `encounter_id`, `person_id`, `t0_date`, `label`, `time_in_hospital`, `readmitted`
   - Row count: 101,766
   - Label prevalence (mean label): 0.1116 (about 11.16% positive class)

## Data quality checks I ran (and results)
Before modeling, I ran three basic checks on the Gold table:

1. **Uniqueness check**
   - Expectation: `encounter_id` should be unique in Gold (one row per encounter)
   - Result:
     - Rows: 101,766
     - Distinct encounter_id: 101,766
     - Duplicates: 0

2. **Label null check**
   - Expectation: `label` should not be missing
   - Result:
     - Label nulls: 0

3. **Range check**
   - Expectation: `time_in_hospital` should be in the valid range [1, 14]
   - Result:
     - Out of range: 0

These checks confirm the Gold table is consistent and safe to use for modeling.

## What I learned today
- How to set up a local analytics “warehouse” using DuckDB.
- Why medallion layers matter: raw data should be preserved, cleaning should be explicit, and modeling tables should be purpose-built.
- Why data-quality checks are required before training models (otherwise models learn from broken data).

## What I will do tomorrow (Day 2)
Tomorrow I will train a baseline predictive model using the Gold table:
- Create a proper train/test split
- Evaluate using PR-AUC (because the positive class is rare)
- Calibrate predicted probabilities so that the scores can be used for real decision thresholds (like top-K outreach)
- Save results and metrics in a simple report
