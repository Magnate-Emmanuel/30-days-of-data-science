#!/usr/bin/env bash
set -euo pipefail
# Day 30 runner that avoids Dropbox/OneDrive file locks on DuckDB by using a local work DB.
# IMPORTANT: if you already ran Day 29 using the local DB, DO NOT overwrite it.
# Run from repo root.

REPO_ROOT="$(pwd)"
SOURCE_DB="$REPO_ROOT/Day-21/db/hospcap.duckdb"

WORK_DIR="${TMPDIR:-/tmp}/hospcap_work"
WORK_DB="$WORK_DIR/hospcap.duckdb"

mkdir -p "$WORK_DIR"

if [ ! -f "$WORK_DB" ]; then
  echo "Work DB not found. Copying repo DB -> $WORK_DB"
  cp -f "$SOURCE_DB" "$WORK_DB"
else
  echo "Using existing work DB (will NOT overwrite): $WORK_DB"
  echo "Tip: this is what you want if Day 29 already ran on the work DB."
fi

pip install -e ./Day-21
python -m hospcap.day30 run --db "$WORK_DB" --report-dir "Day-30/reports"
