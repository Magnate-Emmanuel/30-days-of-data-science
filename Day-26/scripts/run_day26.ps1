\
pip install -e .\Day-21
pip install scikit-learn
python -m hospcap.day26 run --db "Day-21\db\hospcap.duckdb" --report-dir "Day-26\reports" --contract-name "hospcap_state_daily_v1" --targets inpatient_beds_used staffed_adult_icu_bed_occupancy --horizons 1 7 14 --quantiles 0.1 0.5 0.9 --n-splits 8 --step 7
