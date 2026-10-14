from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from bank_reader import check_continuity, read_header

JUNE = Path(__file__).parent / "fixtures" / "2026-06"


@pytest.fixture(scope="module")
def june():
    return read_header(JUNE / "statement_header.json")


def _july(june: dict, **changes) -> dict:
    """A July header that follows June correctly; change only what a test needs."""
    july = dict(june, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
                opening_balance=june["closing_balance"], closing_balance=Decimal("290000.00"))
    july.update(changes)
    return july


def test_june_then_july_chain_correctly(june):
    assert check_continuity([june, _july(june)]) == []


def test_one_statement_alone_passes(june):
    assert check_continuity([june]) == []


def test_no_statements_pass():
    assert check_continuity([]) == []


def test_opening_must_equal_previous_closing_to_the_penny(june):
    july = _july(june, opening_balance=june["closing_balance"] + Decimal("0.01"))
    assert check_continuity([june, july]) == [
        "2026-06-30 -> 2026-07-01: opening balance 285378.58 does not equal "
        "previous closing balance 285378.57"]


def test_missing_month_is_a_gap(june):
    august = _july(june, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31))
    assert check_continuity([june, august]) == [
        "2026-06-30 -> 2026-08-01: gap, no statement for 2026-07-01 to 2026-07-31"]


def test_duplicated_month_is_an_overlap(june):
    assert check_continuity([june, dict(june)]) == [
        "2026-06-30 -> 2026-06-01: overlap, both statements cover 2026-06-01 to 2026-06-30",
        "2026-06-30 -> 2026-06-01: opening balance 250000.00 does not equal "
        "previous closing balance 285378.57"]


def test_different_account_is_reported_once(june):
    other = _july(june, account_id="ACC-OTHER")
    assert check_continuity([june, other]) == [
        "2026-06-30 -> 2026-07-01: account changes from ACC-KRW-CASH-01 to ACC-OTHER"]


def test_every_link_is_checked(june):
    july = _july(june)
    august = _july(july, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
                   opening_balance=Decimal("1.00"))
    problems = check_continuity([june, july, august])
    assert len(problems) == 1 and problems[0].startswith("2026-07-31 -> 2026-08-01")