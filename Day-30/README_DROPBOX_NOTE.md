## Dropbox/OneDrive note (Windows)

If you run Day 29 using a local work DB (`%TEMP%\hospcap_work\hospcap.duckdb`), then **Day 30 must read that same work DB**.

Do **not** overwrite the work DB before running Day 30. The updated `run_day30_localdb.ps1` script now only copies the repo DB if the work DB does not exist.
