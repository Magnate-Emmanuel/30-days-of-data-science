#!/usr/bin/env bash
set -euo pipefail
python -m hospcap.day21 run --db db/hospcap.duckdb --data-dir data --datasets state facility
