from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict

@dataclass(frozen=True)
class DatasetSpec:
    key: str
    dataset_id: str
    name: str
    download_url: str
    table_bronze: str
    table_silver: str
    # heuristic columns (we discover at runtime)
    date_candidates: tuple[str, ...]
    key_candidates: tuple[str, ...]

STATE = DatasetSpec(
    key="state",
    dataset_id="g62h-syeh",
    name="COVID-19 Reported Patient Impact and Hospital Capacity by State Timeseries (RAW)",
    download_url="https://healthdata.gov/api/views/g62h-syeh/rows.csv?accessType=DOWNLOAD",
    table_bronze="bronze.hhs_state_timeseries_raw",
    table_silver="silver.hhs_state_timeseries",
    date_candidates=("date", "report_date", "reporting_date", "collection_date", "as_of_date"),
    key_candidates=("state",),
)

FACILITY = DatasetSpec(
    key="facility",
    dataset_id="uqq2-txqb",
    name="COVID-19 Reported Patient Impact and Hospital Capacity by Facility -- RAW",
    download_url="https://healthdata.gov/api/views/uqq2-txqb/rows.csv?accessType=DOWNLOAD",
    table_bronze="bronze.hhs_facility_raw",
    table_silver="silver.hhs_facility_weekly",
    date_candidates=("collection_week", "week_ending", "date", "report_date"),
    key_candidates=("hospital_pk", "hhs_id", "facility_id"),
)

DATASETS: Dict[str, DatasetSpec] = {d.key: d for d in (STATE, FACILITY)}
