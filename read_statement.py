"""Read a bank statement and check that it adds up on its own.

Current version (v1, deliberately simple):
- Reads the statement header from a JSON file and the transactions from a CSV file.
- Converts dates and money (Decimal, never float) and adds a signed amount:
  positive = money in, negative = money out.
- Rejects bad input with clear messages: missing columns, invalid dates or
  amounts, negative paid_in/paid_out, NaN, more than two decimal places.
- Checks: totals, running balance, dates within the statement period.

Not yet (planned):
- Other input formats (PDF, Excel, MT940, camt.053) through a separate reader
  that produces the same lines.
- Header and lines in one file, as real statements have.
- Lines as dataclasses instead of dictionaries.
- Currencies other than GBP.
- Checking continuity between months (this opening = last month's closing).
"""


from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED_COLUMNS = ["date", "description", "reference", "paid_in", "paid_out", "balance"]
REQUIRED_HEADER_FIELDS = ["account_id", "custodian", "currency", "period_start",
                          "period_end", "opening_balance", "closing_balance"]

def parse_money(text: str, where: str, allow_negative: bool = False) -> Decimal | None:
    text = text.strip()
    if text == "":
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{where}: not a number: {text!r}")
    if not value.is_finite():
        raise ValueError(f"{where}: not a finite number (NaN or Infinity): {text!r}")
    if value.as_tuple().exponent < -2:
        raise ValueError(f"{where}: more than two decimal places: {text!r}")
    if value < 0 and not allow_negative:
        raise ValueError(f"{where}: must not be negative: {text!r}")
    return value

    
def read_header(header_path: Path) -> dict:
    
    with open(header_path, "r", encoding="utf-8") as header_data:
        try:
            header = json.load(header_data)
        except json.JSONDecodeError as error:
            raise ValueError(f"Header file is not valid JSON: {error}")

    missing = [field for field in REQUIRED_HEADER_FIELDS if field not in header]
    if missing:
        raise ValueError(f"Header is missing fields: {missing}")

    for field in ("period_start", "period_end"):
        try:
            header[field] = date.fromisoformat(header[field])
        except (ValueError, TypeError):
            raise ValueError(f"Header {field}: invalid date {header[field]!r}")
    
    for field in ("opening_balance", "closing_balance"):
        value = parse_money(str(header[field]), f"Header {field}", allow_negative=True)
        if value is None:
            raise ValueError(f"Header {field}: is empty")
        header[field] = value

    if header["period_start"] > header["period_end"]:
        raise ValueError("Header: period_start is after period_end")
    if header["currency"] != "GBP":
        raise ValueError(f"Header: only GBP is supported in v1, got {header['currency']!r}")
    return header



def read_lines(lines_path: Path) -> list[dict]:
    lines = []
    with open(lines_path, "r", encoding="utf-8-sig", newline="") as lines_data:
        reader = csv.DictReader(lines_data)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        for line_number, line in enumerate(reader, start=2):
            line["line_number"] = line_number

            try:
                line["date"] = date.fromisoformat(line["date"].strip())
            except ValueError:
                raise ValueError(f"Line {line_number}: invalid date {line['date']!r}")
            
            line["paid_in"] = parse_money(line["paid_in"], f"Line {line_number}: paid_in", allow_negative=False)
            line["paid_out"] = parse_money(line["paid_out"], f"Line {line_number}: paid_out", allow_negative=False)
            line["balance"] = parse_money(line["balance"], f"Line {line_number}: balance", allow_negative=True)

            if line["balance"] is None:
                raise ValueError(f"Line {line_number}: balance is empty")
            if (line["paid_in"] is None) == (line["paid_out"] is None):
                raise ValueError(f"Line {line_number}: needs exactly one of paid_in or paid_out")

            if line["paid_in"] is not None:
                line["amount"] = line["paid_in"]
            else:
                line["amount"] = -line["paid_out"]

            lines.append(line)
    return lines



def check_totals(header: dict, lines:list[dict]) -> tuple[bool,str]:
    
    total = sum(line["amount"] for line in lines)
    expected_closing_balance = header["opening_balance"] + total

    if expected_closing_balance != header["closing_balance"]:
        return False, f"Expected closing balance {expected_closing_balance} does not match actual closing balance {header['closing_balance']}"
    
    return True, "Totals match"



def check_running_balance(header: dict, lines: list[dict]) -> tuple[bool, str]:
    running_balance = header["opening_balance"]

    for line in lines:
        running_balance += line["amount"]
        if running_balance != line["balance"]:
            return False, f"Line {line['line_number']}: expected balance {running_balance} does not match actual balance {line['balance']}"

    return True, "Running balances match"



def check_dates(header: dict, lines: list[dict]) -> tuple[bool, str]:
    for line in lines:
        if line["date"] < header["period_start"] or line["date"] > header["period_end"]:
            return False, f"Line {line['line_number']}: date {line['date']} is outside the statement period {header['period_start']} to {header['period_end']}"

    return True, "All dates are within the statement period"



if __name__ == "__main__":
    header = read_header(Path("tests/fixtures/2026-06/statement_header.json"))
    lines = read_lines(Path("tests/fixtures/2026-06/bank_statement.csv"))

    totals_ok, totals_message = check_totals(header, lines)
    running_ok, running_message = check_running_balance(header, lines)
    dates_ok, dates_message = check_dates(header, lines)

    print("PASS" if totals_ok else "FAIL", "totals:", totals_message)
    print("PASS" if running_ok else "FAIL", "running balance:", running_message)
    print("PASS" if dates_ok else "FAIL", "dates:", dates_message)

    if totals_ok and running_ok and dates_ok:
        print("Statement checks passed")
    else:
        print("Statement checks FAILED: do not reconcile this statement")
