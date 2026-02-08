# Day 27 — Backtest & monitoring summary

Run ID: `dc29c3b2-ffb8-42a7-95a3-9ca506480be9`

Day 26 run_id used: `a0f64e55-b0c3-43bf-95a7-d401fec15810`

Contract: `hospcap_state_daily_v1`

Point metrics use the Day-26 **P50** forecast (closest quantile to 0.5).

## Point accuracy (P50)

| method          | model        | target                          |   horizon |   q_point |      mae |     rmse |    mape |    wape |   n |
|:----------------|:-------------|:--------------------------------|----------:|----------:|---------:|---------:|--------:|--------:|----:|
| gbrt_quantile   | hgb_quantile | inpatient_beds_used             |         1 |       0.5 | 112.303  | 193.023  | 1.60051 | 1.20485 | 376 |
| naive_conformal | naive_last   | inpatient_beds_used             |         7 |       0.5 | 146.537  | 252.933  | 2.7317  | 1.54459 | 376 |
| gbrt_quantile   | hgb_quantile | inpatient_beds_used             |        14 |       0.5 | 197.061  | 332.828  | 3.46105 | 2.08895 | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |         1 |       0.5 |  17.582  |  27.9987 | 3.74375 | 1.81187 | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |         7 |       0.5 |  21.2466 |  31.8817 | 5.06539 | 2.14207 | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |        14 |       0.5 |  26.2698 |  43.3608 | 5.35384 | 2.66986 | 376 |

## Interval reliability (P10/P90)

| method          | model        | target                          |   horizon |   q_lo |   q_hi |   coverage |   mean_width |   median_width |   p90_width |   n |
|:----------------|:-------------|:--------------------------------|----------:|-------:|-------:|-----------:|-------------:|---------------:|------------:|----:|
| gbrt_quantile   | hgb_quantile | inpatient_beds_used             |         1 |    0.1 |    0.9 |   0.773936 |     321.992  |       242.004  |    686.069  | 376 |
| naive_conformal | naive_last   | inpatient_beds_used             |         7 |    0.1 |    0.9 |   0.880319 |     684.75   |       684      |    690      | 376 |
| gbrt_quantile   | hgb_quantile | inpatient_beds_used             |        14 |    0.1 |    0.9 |   0.678191 |     460.366  |       301.927  |   1128.37   | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |         1 |    0.1 |    0.9 |   0.768617 |      47.6247 |        40.1612 |     94.2995 | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |         7 |    0.1 |    0.9 |   0.739362 |      63.762  |        51.0698 |    128.173  | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |        14 |    0.1 |    0.9 |   0.704787 |      67.287  |        56.0186 |    133.183  | 376 |

## Quantile loss (pinball)

| method          | model        | target                          |   horizon |   q |   pinball |   n |
|:----------------|:-------------|:--------------------------------|----------:|----:|----------:|----:|
| gbrt_quantile   | hgb_quantile | inpatient_beds_used             |         1 | 0.1 |  27.6362  | 376 |
| gbrt_quantile   | hgb_quantile | inpatient_beds_used             |         1 | 0.5 |  56.1513  | 376 |
| gbrt_quantile   | hgb_quantile | inpatient_beds_used             |         1 | 0.9 |  24.5325  | 376 |
| naive_conformal | naive_last   | inpatient_beds_used             |         7 | 0.1 |  51.4141  | 376 |
| naive_conformal | naive_last   | inpatient_beds_used             |         7 | 0.5 |  73.2686  | 376 |
| naive_conformal | naive_last   | inpatient_beds_used             |         7 | 0.9 |  47.3774  | 376 |
| gbrt_quantile   | hgb_quantile | inpatient_beds_used             |        14 | 0.1 |  51.6596  | 376 |
| gbrt_quantile   | hgb_quantile | inpatient_beds_used             |        14 | 0.5 |  98.5304  | 376 |
| gbrt_quantile   | hgb_quantile | inpatient_beds_used             |        14 | 0.9 |  40.8768  | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |         1 | 0.1 |   3.86708 | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |         1 | 0.5 |   8.791   | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |         1 | 0.9 |   3.62624 | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |         7 | 0.1 |   4.77989 | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |         7 | 0.5 |  10.6233  | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |         7 | 0.9 |   5.01677 | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |        14 | 0.1 |   6.77338 | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |        14 | 0.5 |  13.1349  | 376 |
| gbrt_quantile   | hgb_quantile | staffed_adult_icu_bed_occupancy |        14 | 0.9 |   5.64108 | 376 |

## Series drift checks (recent=60 days vs baseline=180 days)

The table ranks states by absolute standardized mean shift (z_shift) within each target.

| target                          | state   |   baseline_mean |   recent_mean |   baseline_std |   z_shift |   pct_mean_change |   baseline_missing_rate |   recent_missing_rate |   baseline_n |   recent_n |
|:--------------------------------|:--------|----------------:|--------------:|---------------:|----------:|------------------:|------------------------:|----------------------:|-------------:|-----------:|
| inpatient_beds_used             | AK      |       1008.22   |      922.167  |       39.7017  | -2.16755  |          -8.53538 |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | AS      |         73.2056 |       87.0333 |       10.4635  |  1.32152  |          18.889   |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | ND      |       1418.53   |     1360.12   |       55.3682  | -1.05506  |          -4.1181  |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | VI      |         98.3778 |       88.9333 |       12.6549  | -0.746308 |          -9.60018 |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | HI      |       1902.99   |     1871.15   |       47.0749  | -0.676346 |          -1.6731  |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | NC      |      16736.9    |    16443.6    |      437.965   | -0.669701 |          -1.75244 |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | WI      |       8300.35   |     8090.4    |      338.663   | -0.619937 |          -2.52941 |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | SD      |       1456.19   |     1410.92   |       76.3204  | -0.593187 |          -3.10895 |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | NH      |       2114.99   |     2064.1    |       99.8422  | -0.509749 |          -2.40636 |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | IL      |      19819.4    |    19421.9    |      783.905   | -0.506999 |          -2.00531 |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | CT      |       5829.09   |     5923.92   |      187.214   |  0.506522 |           1.6268  |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | WY      |        571.761  |      549.283  |       46.3006  | -0.485475 |          -3.93132 |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | IN      |      10730.1    |    10464.8    |      564.371   | -0.470042 |          -2.47227 |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | WA      |       9765.02   |     9587.9    |      384.742   | -0.460351 |          -1.81379 |                       0 |                     0 |          180 |         60 |
| inpatient_beds_used             | MI      |      16650.1    |    16889.1    |      626.472   |  0.381448 |           1.43523 |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | AK      |         76.7389 |       66.7    |        7.43592 | -1.35005  |         -13.0819  |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | NE      |        359.15   |      336.483  |       17.692   | -1.28118  |          -6.3112  |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | ND      |        100.1    |       86.5    |       12.8841  | -1.05556  |         -13.5864  |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | CT      |        588.694  |      563.1    |       24.9682  | -1.02508  |          -4.34766 |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | WA      |        846.428  |      812.483  |       33.8027  | -1.00419  |          -4.01032 |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | SC      |        863.122  |      827.033  |       40.3088  | -0.895311 |          -4.1812  |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | TN      |       1641.01   |     1593.97   |       53.422   | -0.880619 |          -2.8668  |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | AZ      |       1096.31   |     1042.05   |       66.6122  | -0.814499 |          -4.94894 |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | OH      |       2522.7    |     2428.35   |      125.41    | -0.752335 |          -3.74004 |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | SD      |        125.856  |      120.033  |        8.13301 | -0.715876 |          -4.62611 |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | WI      |        873.828  |      845.35   |       44.0658  | -0.646255 |          -3.25897 |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | CO      |        755.078  |      735.933  |       30.4424  | -0.628875 |          -2.53543 |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | NM      |        305.733  |      296.267  |       15.298   | -0.618817 |          -3.09638 |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | GA      |       2108.41   |     2018.77   |      145.157   | -0.617571 |          -4.25175 |                       0 |                     0 |          180 |         60 |
| staffed_adult_icu_bed_occupancy | KS      |        539.561  |      522.7    |       31.7291  | -0.531409 |          -3.12497 |                       0 |                     0 |          180 |         60 |

## Backtest drift (early vs late cutoffs)

| method          | target                          |   horizon | period   |      mae |     rmse |    mape |    wape |   n |   coverage |
|:----------------|:--------------------------------|----------:|:---------|---------:|---------:|--------:|--------:|----:|-----------:|
| gbrt_quantile   | inpatient_beds_used             |         1 | early    | 107.011  | 166.182  | 1.56423 | 1.13353 | 188 |   0.771277 |
| gbrt_quantile   | inpatient_beds_used             |         1 | late     | 117.595  | 216.563  | 1.63679 | 1.27802 | 188 |   0.776596 |
| naive_conformal | inpatient_beds_used             |         7 | early    | 139.926  | 251.515  | 2.11665 | 1.46033 | 188 |   0.914894 |
| naive_conformal | inpatient_beds_used             |         7 | late     | 153.149  | 254.344  | 3.34675 | 1.63055 | 188 |   0.845745 |
| gbrt_quantile   | inpatient_beds_used             |        14 | early    | 191.354  | 319.938  | 2.93205 | 2.01239 | 188 |   0.680851 |
| gbrt_quantile   | inpatient_beds_used             |        14 | late     | 202.767  | 345.237  | 3.99005 | 2.16673 | 188 |   0.675532 |
| gbrt_quantile   | staffed_adult_icu_bed_occupancy |         1 | early    |  17.4728 |  28.0086 | 4.27256 | 1.77746 | 188 |   0.755319 |
| gbrt_quantile   | staffed_adult_icu_bed_occupancy |         1 | late     |  17.6912 |  27.9887 | 3.21495 | 1.84719 | 188 |   0.781915 |
| gbrt_quantile   | staffed_adult_icu_bed_occupancy |         7 | early    |  20.1897 |  29.1249 | 5.29118 | 2.01536 | 188 |   0.739362 |
| gbrt_quantile   | staffed_adult_icu_bed_occupancy |         7 | late     |  22.3034 |  34.4184 | 4.8396  | 2.27134 | 188 |   0.739362 |
| gbrt_quantile   | staffed_adult_icu_bed_occupancy |        14 | early    |  23.8826 |  35.9335 | 5.27614 | 2.40411 | 188 |   0.691489 |
| gbrt_quantile   | staffed_adult_icu_bed_occupancy |        14 | late     |  28.657  |  49.6901 | 5.43154 | 2.94078 | 188 |   0.718085 |

