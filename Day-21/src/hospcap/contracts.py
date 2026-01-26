from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

@dataclass(frozen=True)
class Contract:
    name: str
    version: int
    source_table: str
    date_col: str
    key_cols: List[str]
    required_targets: List[str]

def load_contract(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))

def parse_contract(d: Dict[str, Any]) -> Contract:
    targets = d.get("targets", [])
    required_targets = [t["source_column"] for t in targets if t.get("required", False)]
    return Contract(
        name=d.get("name", "unknown"),
        version=int(d.get("version", 1)),
        source_table=d["source"]["duckdb_table"],
        date_col=d["source"]["date_col"],
        key_cols=list(d["source"]["key_cols"]),
        required_targets=required_targets,
    )

def validate_contract_columns(available_cols: List[str], contract: Contract) -> Tuple[bool, List[str]]:
    missing = [c for c in contract.required_targets if c not in available_cols]
    ok = (len(contract.required_targets) == 0) or (len(missing) < len(contract.required_targets))
    # ok means: not *all* required targets are missing.
    return ok, missing
