.PHONY: install day21 clean

install:
	python -m pip install -r requirements.txt

day21:
	python -m hospcap.day21 run --db db/hospcap.duckdb --data-dir data --datasets state facility

clean:
	rm -rf .pytest_cache __pycache__
