"""Tests for FirmFileConnector.get_cash_entries: the firm's cash entries
for one account and one period, as matching will ask for them."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from liquet.door.firm.firm_connector import JsonFirmConnector

JUNE_FIRM = Path(__file__).parent / "fixtures" / "2026-06" / "firm"
ACCOUNT = "ACC-KRW-CASH-01"
JUNE = (date(2026, 6, 1), date(2026, 6, 30))


@pytest.fixture(scope="module")
def connector():
    return JsonFirmConnector(JUNE_FIRM / "accounts.json", JUNE_FIRM / "portfolios.json")


def _ids(entries):
    return [e["entry_id"] for e in entries]


# ---------------- normal case ----------------

def test_june_has_the_sixteen_june_entries(connector):
    entries = connector.get_cash_entries(ACCOUNT, *JUNE)
    assert len(entries) == 16
    assert "CE-2026-05-0030" not in _ids(entries)   # May's interest stays in May


def test_june_entries_reach_the_answer_keys_book_closing(connector):
    # answer_key.json: book_opening 250000.00, book_closing 286683.20.
    # If an entry were missing or extra, this sum would not land on it.
    entries = connector.get_cash_entries(ACCOUNT, *JUNE)
    moved = sum(Decimal(e["debit"] or "0") - Decimal(e["credit"] or "0") for e in entries)
    assert Decimal("250000.00") + moved == Decimal("286683.20")


def test_entries_come_oldest_first(connector):
    entries = connector.get_cash_entries(ACCOUNT, *JUNE)
    assert _ids(entries)[:3] == ["CE-2026-06-0001", "CE-2026-06-0002", "CE-2026-06-0003"]
    assert [e["date"] for e in entries] == sorted(e["date"] for e in entries)


# ---------------- boundaries ----------------

def test_first_and_last_day_are_included(connector):
    first = connector.get_cash_entries(ACCOUNT, date(2026, 6, 1), date(2026, 6, 1))
    last = connector.get_cash_entries(ACCOUNT, date(2026, 6, 30), date(2026, 6, 30))
    assert _ids(first) == ["CE-2026-06-0001", "CE-2026-06-0002"]
    assert len(last) == 5   # the five management fees, 30 June


def test_may_asks_for_mays_interest(connector):
    assert _ids(connector.get_cash_entries(ACCOUNT, date(2026, 5, 1), date(2026, 5, 31))) == [
        "CE-2026-05-0030"]


def test_period_with_no_entries_gives_empty_list(connector):
    assert connector.get_cash_entries(ACCOUNT, date(2026, 8, 1), date(2026, 8, 31)) == []


def test_trade_agreed_in_june_settling_in_july_is_in_june(connector):
    # Its date is the trade date (29 June); the bank pays it 1 July (break B2).
    assert "CE-2026-06-0011" in _ids(connector.get_cash_entries(ACCOUNT, *JUNE))


def test_recorded_late_still_belongs_to_its_date(connector):
    # CE-2026-06-0007 happened 18 June but was entered 19 June.
    [entry] = connector.get_cash_entries(ACCOUNT, date(2026, 6, 18), date(2026, 6, 18))
    assert (entry["entry_id"], entry["recorded_at"]) == ("CE-2026-06-0007", "2026-06-19")


# ---------------- silent wrong ----------------

def test_changing_a_returned_entry_does_not_change_the_data(connector):
    [entry, *_] = connector.get_cash_entries(ACCOUNT, *JUNE)
    entry["debit"] = "0.00"
    [again, *_] = connector.get_cash_entries(ACCOUNT, *JUNE)
    assert again["debit"] == "25000.00"


def test_only_the_asked_account_is_returned(tmp_path):
    # The June fixture has one account, so it can't catch entries from
    # another account slipping in. Two accounts, one June movement each.
    def account(account_id, movement_id):
        return {"account_id": account_id, "name": "N", "custodian": "C", "currency": "GBP",
                "cash_balances": [], "account_movements": [{
                    "movement_id": movement_id, "value_date": "2026-06-30",
                    "entered_on": "2026-06-30", "kind": "INTEREST", "narrative": "Interest",
                    "our_ref": "INT", "direction": "IN", "amount": "1.00"}]}
    (tmp_path / "accounts.json").write_text(
        json.dumps([account("A1", "M-A1"), account("A2", "M-A2")]), encoding="utf-8")
    (tmp_path / "portfolios.json").write_text("[]", encoding="utf-8")
    connector = JsonFirmConnector(tmp_path / "accounts.json", tmp_path / "portfolios.json")
    assert _ids(connector.get_cash_entries("A1", *JUNE)) == ["M-A1"]
    assert _ids(connector.get_cash_entries("A2", *JUNE)) == ["M-A2"]


# ---------------- bad input ----------------

def test_unknown_account_raises(connector):
    # Silent wrong otherwise: a typo in the account id would give [] and
    # every bank line would look unmatched.
    with pytest.raises(ValueError, match="unknown account 'ACC-TYPO'; known: ACC-KRW-CASH-01"):
        connector.get_cash_entries("ACC-TYPO", *JUNE)


def test_start_after_end_raises(connector):
    with pytest.raises(ValueError, match="start 2026-06-30 is after end 2026-06-01"):
        connector.get_cash_entries(ACCOUNT, date(2026, 6, 30), date(2026, 6, 1))