#!/usr/bin/env bash
set -euo pipefail
# From repo root:
pip install -e ./Day-21

python -m hospcap.day29 run   --db "Day-21/db/hospcap.duckdb"   --report-dir "Day-29/reports"   --contract-name "hospcap_state_daily_v1"
