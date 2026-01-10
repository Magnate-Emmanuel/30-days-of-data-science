# Day 14 — Leakage-safe train/valid/test splits (No-show project)

## Goal
Create train/validation/test splits that avoid data leakage by ensuring the same patient never appears in more than one split. This is required for honest evaluation because patient-level patterns can be memorized if the same person appears in train and test.

## What I built today
I created patient-level splits for the no-show dataset (gold features table), and verified:

- No patient overlap across train/valid/test
- Reasonable split sizes
- Similar label prevalence across splits (no-show rate)

This produces a stable foundation for Day 15 (training predictive models + calibration) and later causal/uplift work.

## Key results (checks)
Patient overlap across splits:
- n_people_in_multiple_splits = 0  ✅

Split summary:

- Train: rows = 77,368; people = 43,579; no-show prevalence = 0.203017  
- Valid: rows = 16,649; people = 9,307; no-show prevalence = 0.203496  
- Test : rows = 16,499; people = 9,410; no-show prevalence = 0.194921  

Interpretation:
- The split is leakage-safe at the person level.
- Prevalence is stable across train/valid/test (test is slightly lower but close), which is good for model development and evaluation.

## Outputs saved
- Split tables in DuckDB (train/valid/test) based on person_id
- A split summary/check cell verifying zero patient overlap and reporting split prevalence

## Notes / decisions
- Splitting unit: person_id (patient-level split)
- Purpose: prevent leakage from repeated patients across splits
- Tomorrow (Day 15): train predictive baselines on train, tune/calibrate on valid, evaluate once on test.
