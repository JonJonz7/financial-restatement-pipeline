import duckdb
import yaml

from quality.check_contracts import CONTRACT_DIR, check_contract

CONTRACT = yaml.safe_load((CONTRACT_DIR / "filing_contract.yml").read_text())


def test_contract_catches_violations(db, companyfacts):
    from ingestion.edgar_client import extract_financial_metrics
    from ingestion.loader import load_raw_financial_facts

    load_raw_financial_facts(extract_financial_metrics(companyfacts), db)
    con = duckdb.connect(db)
    con.execute(
        "update bronze.raw_financial_facts set period_start = date '2030-01-01' "
        "where metric = 'Revenues'"
    )
    results = {r.check: r for r in check_contract(con, CONTRACT, freshness=False)}
    con.close()
    assert not results["rule period_order"].passed
    assert not results["volume"].passed  # only 4 rows, contract wants 100
    assert results["cik: pattern"].passed


def test_missing_table_is_an_error(tmp_path):
    con = duckdb.connect(str(tmp_path / "empty.duckdb"))
    [r] = check_contract(con, CONTRACT)
    assert not r.passed and r.level == "error"
