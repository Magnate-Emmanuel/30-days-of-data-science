\
# Day 30 runner that avoids Dropbox/OneDrive file locks on DuckDB by using a local work DB.
# IMPORTANT: if you already ran Day 29 using the local DB, DO NOT overwrite it.
# Run from repo root (PowerShell).

$RepoRoot = (Get-Location).Path
$SourceDb = Join-Path $RepoRoot "Day-21\db\hospcap.duckdb"

# Local, non-synced work directory (TEMP is fine)
$WorkDir = Join-Path $env:TEMP "hospcap_work"
$WorkDb  = Join-Path $WorkDir "hospcap.duckdb"

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

if (-Not (Test-Path $WorkDb)) {
  Write-Host "Work DB not found. Copying repo DB -> $WorkDb"
  Copy-Item -Force $SourceDb $WorkDb
} else {
  Write-Host "Using existing work DB (will NOT overwrite): $WorkDb"
  Write-Host "Tip: this is what you want if Day 29 already ran on the work DB."
}

pip install -e .\Day-21
python -m hospcap.day30 run --db $WorkDb --report-dir "Day-30\reports"
