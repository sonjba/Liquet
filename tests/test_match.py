from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from bank_prepare import bank_to_item
from bank_reader import read_statement
from firm_connector import FirmFileConnector
from firm_prepare import firm_to_item
from match import match

JUNE = Path(__file__).parent / "fixtures" / "2026-06"


# ---------------- helpers ----------------

def _item(side: str, item_id: str, **changes) -> dict:
    """A matching item; change only what a test needs."""
    item = {"id": item_id, "side": side,
            "date": date(2026, 6, 10), "expected_date": date(2026, 6, 10),
            "amount": Decimal("100.00"), "reference": "REF-1",
            "entry_type": "SUBSCRIPTION", "description": "test"}
    item.update(changes)
    return item


def _bank(**changes) -> dict:
    return _item("bank", "B1", **changes)


def _firm(item_id: str = "F1", **changes) -> dict:
    return _item("firm", item_id, **changes)


def _pairs(result: dict) -> dict[str, str]:
    """{bank_id: firm_id} for every decision."""
    return {d["bank_id"]: d["firm_id"] for d in result["decisions"]}


def _short(bank_id: str) -> str:
    return bank_id.split(":")[-1]          # "ACC-KRW-CASH-01:2026-06:L3" -> "L3"


@pytest.fixture(scope="module")
def june_result():
    header, lines = read_statement(JUNE / "statement_header.json", JUNE / "bank_statement.csv")
    firm = FirmFileConnector(JUNE / "firm" / "accounts.json", JUNE / "firm" / "portfolios.json")
    trades = {t["trade_id"]: t for t in firm.canonical["trades"]}
    entries = firm.get_cash_entries(header["account_id"], header["period_start"], header["period_end"])
    return match([bank_to_item(line) for line in lines],
                 [firm_to_item(entry, trades) for entry in entries])


# ---------------- R1 on June ----------------

R1_JUNE_PAIRS = {
    "L2": "CE-2026-06-0001", "L3": "CE-2026-06-0002", "L4": "CE-2026-06-0003",
    "L6": "CE-2026-06-0005", "L7": "CE-2026-06-0006", "L9": "CE-2026-06-0009",
    "L10": "CE-2026-06-0010",
}


def test_r1_pairs_exactly_the_expected_june_lines(june_result):
    pairs = {_short(b): f for b, f in _pairs(june_result).items()}
    assert pairs == R1_JUNE_PAIRS


def test_every_r1_decision_is_congruit_with_no_differences(june_result):
    for decision in june_result["decisions"]:
        assert decision["verdict"] == "CONGRUIT"
        assert decision["rule"] == "R1"
        assert decision["differences"] == []


def test_lines_r1_cannot_settle_are_left_for_later_rules(june_result):
    left = {_short(item["id"]) for item in june_result["unmatched_bank"]}
    assert left == {"L5", "L8", "L11", "L12", "L13"}


def test_firm_entries_r1_cannot_settle_are_left_for_later_rules(june_result):
    left = {item["id"] for item in june_result["unmatched_firm"]}
    assert left == {"CE-2026-06-0004", "CE-2026-06-0007", "CE-2026-06-0008",
                    "CE-2026-06-0011", "CE-2026-06-0012", "CE-2026-06-0013",
                    "CE-2026-06-0014", "CE-2026-06-0015", "CE-2026-06-0016"}


def test_settlement_is_compared_with_its_settlement_date(june_result):
    # L3 is 3 June at the bank; the firm booked it 1 June but expects 3 June.
    decision = next(d for d in june_result["decisions"] if _short(d["bank_id"]) == "L3")
    assert decision["evidence"]["lag_days"] == 0


def test_one_day_lag_is_recorded_in_the_evidence(june_result):
    # L6: bank 12 June, firm 11 June.
    decision = next(d for d in june_result["decisions"] if _short(d["bank_id"]) == "L6")
    assert decision["evidence"]["lag_days"] == 1


# ---------------- R1 boundaries ----------------

@pytest.mark.parametrize("bank_day, matches", [
    (date(2026, 6, 9), True),     # one day early
    (date(2026, 6, 11), True),    # one day late
    (date(2026, 6, 8), False),    # two days early
    (date(2026, 6, 12), False),   # two days late
])
def test_date_tolerance_is_one_day_either_way(bank_day, matches):
    result = match([_bank(date=bank_day)], [_firm()])
    assert bool(result["decisions"]) == matches


def test_different_amount_is_not_r1():
    result = match([_bank(amount=Decimal("90.00"))], [_firm()])
    assert result["decisions"] == []


def test_opposite_sign_is_not_a_match():
    # Money in at the bank must never pair with money out at the firm.
    result = match([_bank(amount=Decimal("100.00"))], [_firm(amount=Decimal("-100.00"))])
    assert result["decisions"] == []


def test_missing_reference_on_both_sides_is_not_a_match():
    result = match([_bank(reference=None)], [_firm(reference=None)])
    assert result["decisions"] == []


def test_two_firm_items_with_the_same_reference_are_left_alone():
    # A group (one bank line, several entries) is R3's job, not R1's.
    result = match([_bank()], [_firm("F1"), _firm("F2")])
    assert result["decisions"] == []
    assert len(result["unmatched_firm"]) == 2


def test_a_firm_item_is_used_only_once():
    # Two identical bank lines, one firm entry: only one pair.
    first, second = _bank(), _item("bank", "B2")
    result = match([first, second], [_firm()])
    assert len(result["decisions"]) == 1
    assert [item["id"] for item in result["unmatched_bank"]] == ["B2"]


def test_match_does_not_change_the_lists_it_was_given():
    bank_items, firm_items = [_bank()], [_firm()]
    match(bank_items, firm_items)
    assert len(bank_items) == 1 and len(firm_items) == 1