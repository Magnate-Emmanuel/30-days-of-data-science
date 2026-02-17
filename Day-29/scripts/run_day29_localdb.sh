#!/usr/bin/env bash
set -euo pipefail
# Day 29 runner that avoids Dropbox/OneDrive file locks on DuckDB by using a local work DB.
# Run from repo root.

REPO_ROOT="$(pwd)"
SOURCE_DB="$REPO_ROOT/Day-21/db/hospcap.duckdb"

WORK_DIR="${TMPDIR:-/tmp}/hospcap_work"
WORK_DB="$WORK_DIR/hospcap.duckdb"

mkdir -p "$WORK_DIR"
cp -f "$SOURCE_DB" "$WORK_DB"

pip install -e ./Day-21

python -m hospcap.day29 run   --db "$WORK_DB"   --report-dir "Day-29/reports"   --contract-name "hospcap_state_daily_v1"

# OPTIONAL: copy results back
# cp -f "$WORK_DB" "$SOURCE_DB"
