# Note: DuckDB + Dropbox/OneDrive file locks (Windows)

If your repository lives under **Dropbox** or **OneDrive**, you may occasionally see:

> IO Error: Cannot open file ... The process cannot access the file because it is being used by another process.  
> File is already open in ... Dropbox.exe

This is not a code bug: DuckDB uses OS-level file locks, and sync clients sometimes hold files briefly while scanning/uploading.

## Recommended fix

Keep the DuckDB database **outside** the synced folder and point `--db` to that path, for example:

- `C:\hospcap_work\db\hospcap.duckdb`
- `%TEMP%\hospcap_work\hospcap.duckdb`

We included helper scripts:

- `Day-29/scripts/run_day29_localdb.ps1` (Windows PowerShell)
- `Day-29/scripts/run_day29_localdb.sh` (bash)

These scripts copy the repo DB to a local work DB, run the pipeline, and optionally copy results back.

## Alternative

Pause/quit Dropbox (or OneDrive) syncing while running the pipeline, then resume after.
