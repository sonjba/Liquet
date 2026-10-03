from datetime import date
from decimal import Decimal
from pathlib import Path

import read_statement

JUNE = Path(__file__).parent / "fixtures" / "2026-06"

def test_june_header_is_read_correctly():
    header = read_statement.read_header(JUNE / "statement_header.json")
    assert header["account_id"] == "ACC-KRW-CASH-01"
    assert header["custodian"] == "Northgate Custody Bank"
    assert header["currency"] == "GBP"
    assert header["period_start"] == date(2026, 6, 1)
    assert header["period_end"] == date(2026, 6, 30)
    assert header["opening_balance"] == Decimal("250000.00")
    assert header["closing_balance"] == Decimal("285378.57")

def test_june_lines_are_read_correctly():
    lines = read_statement.read_lines(JUNE / "bank_statement.csv")
    assert len(lines) == 12
    assert lines[0]["date"] == date(2026, 6, 1)
    assert lines[0]["description"] == "SUBSCRIPTION CL-001 HART A"
    assert lines[0]["reference"] == "CL-001-SUB-0601"
    assert lines[0]["paid_in"] == Decimal("25000.00")
    assert lines[0]["paid_out"] is None
    assert lines[0]["balance"] == Decimal("275000.00")