#!/usr/bin/env bash
set -euo pipefail
pip install -e ./Day-21
python -m hospcap.day27 run --db "Day-21/db/hospcap.duckdb" --report-dir "Day-27/reports" --contract-name "hospcap_state_daily_v1"
