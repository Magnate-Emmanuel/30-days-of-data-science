# Day 26 — Probabilistic forecast summary

Run ID: `f7e63977-795c-4610-ab3c-4b1f523fdfb1`

Targets: inpatient_beds_used, staffed_adult_icu_bed_occupancy

Horizons: 1, 7, 14

Quantiles: 0.1, 0.5, 0.9

Splits: n_splits=8, step_days=7

## Champion method policy

- inpatient_beds_used @ h=7: naive_conformal (baseline champion from Day 25)
- all other target/horizon: gbrt_quantile

## Calibration (interval coverage + width; lower is better for pinball)

| target                          |   horizon | method          |   coverage_80 |   mean_width_80 |   pinball_q10 |   pinball_q50 |   pinball_q90 |   n |
|:--------------------------------|----------:|:----------------|--------------:|----------------:|--------------:|--------------:|--------------:|----:|
| inpatient_beds_used             |         1 | gbrt_quantile   |      0.773936 |        321.992  |           nan |           nan |           nan | 376 |
| inpatient_beds_used             |         7 | naive_conformal |      0.880319 |        684.75   |           nan |           nan |           nan | 376 |
| inpatient_beds_used             |        14 | gbrt_quantile   |      0.678191 |        460.366  |           nan |           nan |           nan | 376 |
| staffed_adult_icu_bed_occupancy |         1 | gbrt_quantile   |      0.768617 |         47.6247 |           nan |           nan |           nan | 376 |
| staffed_adult_icu_bed_occupancy |         7 | gbrt_quantile   |      0.739362 |         63.762  |           nan |           nan |           nan | 376 |
| staffed_adult_icu_bed_occupancy |        14 | gbrt_quantile   |      0.704787 |         67.287  |           nan |           nan |           nan | 376 |

Notes:
- coverage_80 is empirical coverage of [P10, P90]. Ideal ≈ 0.80.
- mean_width_80 is average (P90 − P10); smaller is sharper but should not under-cover.
- pinball losses summarize quantile accuracy (lower is better).
