"""The July fixture: written to continue June's story, and to agree with both answer keys."""

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from liquet.door.bank.bank_reader import check_continuity, read_header, read_statement
from run_month import main as run_month
from liquet.review.work_list import open_items

FIXTURES = Path(__file__).parent / "fixtures"
JUNE, JULY = FIXTURES / "2026-06", FIXTURES / "2026-07"
JULY_FILES = {"header": JULY / "statement_header.json", "lines": JULY / "bank_statement.csv",
              "accounts": JULY / "firm" / "accounts.json",
              "portfolios": JULY / "firm" / "portfolios.json"}


def key(month):
    return json.loads((month / "answer_key.json").read_text(encoding="utf-8"))


def test_july_reads_and_follows_on_from_june():
    read_statement(JULY / "statement_header.json", JULY / "bank_statement.csv")  # its own checks
    june = read_header(JUNE / "statement_header.json")
    july = read_header(JULY / "statement_header.json")
    assert check_continuity([june, july]) == []


def test_junes_two_items_in_transit_clear_on_1_july():
    _, lines = read_statement(JULY / "statement_header.json", JULY / "bank_statement.csv")
    first_day = [line for line in lines if line["date"] == date(2026, 7, 1)]
    assert {line["reference"] for line in first_day} == {"CL-005-SUB-0619", "TR-26062901"}
    assert first_day[-1]["balance"] == Decimal(key(JUNE)["balances"]["true_cash_balance"])


def test_julys_book_opens_where_junes_corrected_book_closed():
    assert key(JULY)["balances"]["book_opening"] == key(JUNE)["balances"]["true_cash_balance"]
    balances = key(JULY)["balances"]
    assert balances["adjusted_bank"] == balances["adjusted_book"]


def test_july_leaves_the_carried_items_and_both_breaks_open(tmp_path):
    run = run_month(JULY_FILES, tmp_path, datetime(2026, 8, 3, tzinfo=timezone.utc))["folder"]
    assert {item["item_id"] for item in open_items(run)} == {
        "ACC-KRW-CASH-01:2026-07:L2", "ACC-KRW-CASH-01:2026-07:L3",   # June's, carried
        "ACC-KRW-CASH-01:2026-07:L6", "CE-2026-07-0003",              # B1, the Reid pair
        "ACC-KRW-CASH-01:2026-07:L9"}                                 # B2, the custody fee