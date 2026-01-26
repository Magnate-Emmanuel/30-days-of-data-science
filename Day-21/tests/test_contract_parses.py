from pathlib import Path
from hospcap.contracts import load_contract, parse_contract

def test_contract_parses():
    d = load_contract(Path("contracts/forecasting_contract_v1.yml"))
    c = parse_contract(d)
    assert c.name
    assert c.version >= 1
    assert c.source_table
    assert c.date_col
    assert len(c.key_cols) >= 1
