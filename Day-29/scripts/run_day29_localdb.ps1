\
# Day 29 runner that avoids Dropbox/OneDrive file locks on DuckDB by using a local work DB.
# Run from repo root (PowerShell).

$RepoRoot = (Get-Location).Path
$SourceDb = Join-Path $RepoRoot "Day-21\db\hospcap.duckdb"

# Choose a local, non-synced work directory (TEMP is fine)
$WorkDir = Join-Path $env:TEMP "hospcap_work"
$WorkDb  = Join-Path $WorkDir "hospcap.duckdb"

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
Copy-Item -Force $SourceDb $WorkDb

pip install -e .\Day-21

python -m hospcap.day29 run `
  --db $WorkDb `
  --report-dir "Day-29\reports" `
  --contract-name "hospcap_state_daily_v1"

# OPTIONAL: copy results back into the repo DB (may fail if Dropbox is syncing).
# If it fails, pause Dropbox sync briefly or quit Dropbox, then re-run the copy.
# Copy-Item -Force $WorkDb $SourceDb
