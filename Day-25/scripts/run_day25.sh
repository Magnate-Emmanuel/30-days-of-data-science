#!/usr/bin/env bash
set -euo pipefail
pip install -e ./Day-21
python -m hospcap.day25 run --db "Day-21/db/hospcap.duckdb" --report-dir "Day-25/reports" --contract-name "hospcap_state_daily_v1" --targets inpatient_beds_used staffed_adult_icu_bed_occupancy --horizons 1 7 14 --n-splits 8 --step 7
