from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest
import read_statement
import re

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
HEADER_ROW = "date,description,reference,paid_in,paid_out,balance\n"
CASES = Path(__file__).parent / "fixtures" / "cases"

# NORMAL CASES (assertions check that the data is read correctly) assert

# Regression: list(reader) once used up the reader, so values stayed text;
# a missing enumerate unpacking broke every line; Decimal("") failed on empty cells.
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


# BOUNDARY CASES (assertions check that the data is rejected correctly) tmp_path
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

# Regression: a negative paid_out was silently flipped into money in.
def test_negative_paid_out_is_rejected(tmp_path):
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text(
        HEADER_ROW + "2026-06-01,CUSTODY FEE,NCB-FEE-0601,,-45.00,955.00\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not be negative"):
        read_statement.read_lines(csv_file)

# Regression: Decimal accepts "NaN"; the error message was first put in the wrong branch.
def test_nan_amount_is_rejected(tmp_path):
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text(
        HEADER_ROW + "2026-06-01,SUBSCRIPTION CL-001,CL-001-SUB-0601,NaN,,1100.00\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not a finite number"):
        read_statement.read_lines(csv_file)


# SILENT WRONGS (assertions check that the data is rejected correctly) pytest.raises
def test_cancelling_errors_fool_totals_but_not_running_balance():
    case = "check_fail_running_balance_errors_cancel_in_totals"
    header = read_statement.read_header(CASES / "checks" / f"{case}.json")
    lines = read_statement.read_lines(CASES / "checks" / f"{case}.csv")

    totals_ok, totals_message = read_statement.check_totals(header, lines)
    assert totals_ok, totals_message        # the trap: totals is fooled

    running_ok, running_message = read_statement.check_running_balance(header, lines)
    assert not running_ok                   # the catch
    assert "Line 2" in running_message      # and it points at the right line

def test_wrong_closing_balance_fails_totals_only():
    header = read_statement.read_header(CASES / "checks" / "check_fail_totals_closing_balance_wrong.json")
    lines = read_statement.read_lines(CASES / "checks" / "check_fail_totals_closing_balance_wrong.csv")

    totals_ok, totals_message = read_statement.check_totals(header, lines)
    assert not totals_ok
    assert "1224.50" in totals_message   # what the lines add up to
    assert "1224.00" in totals_message   # what the header claims

    running_ok, running_message = read_statement.check_running_balance(header, lines)
    assert running_ok, running_message

# BAD INPUTS (assertions check that the data is rejected correctly) pytest.raises + parametrize
@pytest.mark.parametrize("file_name, expected", [
    # amounts
    ("error_negative_paid_out.csv", "Line 3: paid_out: must not be negative"),
    ("error_negative_paid_in.csv", "Line 3: paid_in: must not be negative"),
    ("error_paid_in_nan.csv", "Line 3: paid_in: not a finite number"),
    ("error_paid_in_infinity.csv", "Line 3: paid_in: not a finite number"),
    ("error_three_decimals.csv", "Line 3: paid_in: more than two decimal places"),
    ("error_thousands_separator.csv", "Line 3: paid_in: not a number"),
    ("error_european_decimal_comma.csv", "Line 3: paid_in: not a number"),
    ("error_pound_sign_in_amount.csv", "Line 3: paid_in: not a number"),
    ("error_letters_in_amount.csv", "Line 3: paid_in: not a number"),
    # dates
    ("error_date_dd_mm_yyyy.csv", "Line 3: invalid date"),
    ("error_date_empty_commas_only.csv", "Line 3: invalid date"),
    # paid_in / paid_out / balance rules
    ("error_both_paid_in_and_out.csv", "Line 3: needs exactly one of paid_in or paid_out"),
    ("error_neither_paid_in_nor_out.csv", "Line 3: needs exactly one of paid_in or paid_out"),
    ("error_balance_empty.csv", "Line 3: balance is empty"),
    # columns and file shape
    ("error_column_misspelled_with_data.csv", "Missing columns: ['paid_out']"),
    ("error_column_misspelled_no_data.csv", "Missing columns: ['paid_out']"),
    ("error_column_missing_balance.csv", "Missing columns: ['balance']"),
    ("error_semicolon_separated.csv", "Missing columns"),
    ("error_empty_file.csv", "Missing columns"),
])
def test_bad_lines_file_is_rejected(file_name, expected):
    with pytest.raises(ValueError, match=re.escape(expected)):
        read_statement.read_lines(CASES / "lines" / file_name)

# Regression: Excel's invisible BOM broke the first column name (see ok_bom_from_excel.csv).
@pytest.mark.parametrize("file_name", [
    "ok_negative_balance_overdrawn.csv",
    "ok_header_only_no_transactions.csv",
    "ok_bom_from_excel.csv",
    "ok_columns_in_different_order.csv",
    "ok_extra_column_is_ignored.csv",
    "ok_pound_sign_in_description.csv",
])
def test_valid_lines_file_is_read(file_name):
    read_statement.read_lines(CASES / "lines" / file_name)


# REGRESSION TESTS (assertions check that the data is rejected correctly)
@pytest.mark.parametrize("file_name, expected", [
    ("error_header_missing_closing_balance.json", "Header is missing fields: ['closing_balance']"),
    ("error_header_missing_account_id.json", "Header is missing fields: ['account_id']"),
    ("error_header_opening_balance_not_a_number.json", "Header opening_balance: not a number"),
    ("error_header_opening_balance_empty.json", "Header opening_balance: is empty"),
    ("error_header_closing_balance_nan.json", "Header closing_balance: not a finite number"),
    ("error_header_period_end_wrong_format.json", "Header period_end: invalid date"),
    ("error_header_period_reversed.json", "period_start is after period_end"),
    ("error_header_currency_eur.json", "only GBP is supported"),
    ("error_header_invalid_json.json", "not valid JSON"),
])
def test_bad_header_file_is_rejected(file_name, expected):
    with pytest.raises(ValueError, match=re.escape(expected)):
        read_statement.read_header(CASES / "headers" / file_name)


def test_valid_header_file_is_read():
    header = read_statement.read_header(CASES / "headers" / "ok_header.json")
    assert header["opening_balance"] == Decimal("1000.00")
    assert header["closing_balance"] == Decimal("1224.50")


def test_lines_on_first_and_last_day_of_period_pass_dates_check(tmp_path):
    header = read_statement.read_header(JUNE / "statement_header.json")
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text(
        HEADER_ROW
        + "2026-06-01,FIRST DAY OF PERIOD,REF-1,100.00,,250100.00\n"
        + "2026-06-30,LAST DAY OF PERIOD,REF-2,,50.00,250050.00\n",
        encoding="utf-8",
    )
    lines = read_statement.read_lines(csv_file)

    dates_ok, dates_message = read_statement.check_dates(header, lines)
    assert dates_ok, dates_message


def test_line_after_period_end_fails_dates_check():
    case = "check_fail_dates_outside_period"
    header = read_statement.read_header(CASES / "checks" / f"{case}.json")
    lines = read_statement.read_lines(CASES / "checks" / f"{case}.csv")

    dates_ok, dates_message = read_statement.check_dates(header, lines)
    assert not dates_ok