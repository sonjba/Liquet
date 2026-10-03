from datetime import date
from decimal import Decimal
from pathlib import Path

import read_statement

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
HEADER_ROW = "date,description,reference,paid_in,paid_out,balance\n"

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

def test_statement_with_no_transactions_gives_empty_list(tmp_path):
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text(HEADER_ROW, encoding="utf-8")

    lines = read_statement.read_lines(csv_file)

    assert lines == []

def test_statement_with_negative_balance(tmp_path):
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text(
        HEADER_ROW + "2026-06-01,WITHDRAWAL CL-004,CL-004-WD-0601,,100.00,-100.00\n",
        encoding="utf-8",
    )

    lines = read_statement.read_lines(csv_file)

    assert len(lines) == 1
    assert lines[0]["amount"] == Decimal("-100.00")
    assert lines[0]["balance"] == Decimal("-100.00")

def test_statement_with_one_transaction(tmp_path):
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text(
        HEADER_ROW + "2026-06-01,SUBSCRIPTION CL-001,CL-001-SUB-0601,100.00,,1100.00\n",
        encoding="utf-8",
    )

    lines = read_statement.read_lines(csv_file)

    assert len(lines) == 1
    assert lines[0]["amount"] == Decimal("100.00")
    assert lines[0]["balance"] == Decimal("1100.00")