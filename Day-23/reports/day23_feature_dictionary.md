# Day 23 — Feature dictionary

Targets: inpatient_beds_used, icu_beds_used

Calendar features: `dow`, `week_of_year`, `month`, `year`, `is_weekend`, `is_holiday`

Forward fill policy: `*_ffill3` = COALESCE(y, lag1..lag3)

## inpatient_beds_used

- `inpatient_beds_used_ffill3`: forward-filled value (<= 3 days)
- `inpatient_beds_used_lag1`, `inpatient_beds_used_lag7`, `inpatient_beds_used_lag14`, `inpatient_beds_used_lag21`: lagged ffill values
- `inpatient_beds_used_d1`, `inpatient_beds_used_d7`: deltas on ffill
- `inpatient_beds_used_roll7_mean/sd/max`, `inpatient_beds_used_roll14_mean/sd/max`, `inpatient_beds_used_roll28_mean/sd/max`: rolling stats on ffill

## icu_beds_used

- `icu_beds_used_ffill3`: forward-filled value (<= 3 days)
- `icu_beds_used_lag1`, `icu_beds_used_lag7`, `icu_beds_used_lag14`, `icu_beds_used_lag21`: lagged ffill values
- `icu_beds_used_d1`, `icu_beds_used_d7`: deltas on ffill
- `icu_beds_used_roll7_mean/sd/max`, `icu_beds_used_roll14_mean/sd/max`, `icu_beds_used_roll28_mean/sd/max`: rolling stats on ffill

