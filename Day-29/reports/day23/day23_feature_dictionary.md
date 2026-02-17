# Day 23 — Feature dictionary

Targets: inpatient_beds_used, staffed_adult_icu_bed_occupancy

Calendar features: `dow`, `week_of_year`, `month`, `year`, `is_weekend`, `is_holiday`

Forward fill policy: `*_ffill3` = COALESCE(y, lag1..lag3)

## inpatient_beds_used

- `inpatient_beds_used_ffill3`: forward-filled value (<= 3 days)
- `inpatient_beds_used_lag1`, `inpatient_beds_used_lag7`, `inpatient_beds_used_lag14`, `inpatient_beds_used_lag21`: lagged ffill values
- `inpatient_beds_used_d1`, `inpatient_beds_used_d7`: deltas on ffill
- `inpatient_beds_used_roll7_mean/sd/max`, `inpatient_beds_used_roll14_mean/sd/max`, `inpatient_beds_used_roll28_mean/sd/max`: rolling stats on ffill

## staffed_adult_icu_bed_occupancy

- `staffed_adult_icu_bed_occupancy_ffill3`: forward-filled value (<= 3 days)
- `staffed_adult_icu_bed_occupancy_lag1`, `staffed_adult_icu_bed_occupancy_lag7`, `staffed_adult_icu_bed_occupancy_lag14`, `staffed_adult_icu_bed_occupancy_lag21`: lagged ffill values
- `staffed_adult_icu_bed_occupancy_d1`, `staffed_adult_icu_bed_occupancy_d7`: deltas on ffill
- `staffed_adult_icu_bed_occupancy_roll7_mean/sd/max`, `staffed_adult_icu_bed_occupancy_roll14_mean/sd/max`, `staffed_adult_icu_bed_occupancy_roll28_mean/sd/max`: rolling stats on ffill

