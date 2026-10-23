from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from liquet.door.firm.firm_connector import JsonFirmConnector
from liquet.matching.firm_prepare import (domiciles_by_ticker, expected_date, firm_to_item,
                          parties_by_portfolio, signed_amount)

JUNE_FIRM = Path(__file__).parent.parent / "fixtures" / "2026-06" / "firm"
ITEM_KEYS = {"id", "side", "date", "expected_date", "amount",
             "reference", "entry_type", "description", "party", "domicile"}


# ---------------- helpers ----------------

def _entry(**changes) -> dict:
    """A canonical cash entry (a June subscription); change only what a test needs."""
    entry = {
        "entry_id": "CE-TEST-0001", "date": "2026-06-01", "recorded_at": "2026-06-01",
        "entry_type": "SUBSCRIPTION", "description": "Subscription",
        "reference": "REF-1", "trade_id": None, "ticker": None,
        "account_id": "ACC-1", "portfolio_id": "PF-1", "source": "test",
        "debit": "25000.00", "credit": None,
    }
    entry.update(changes)
    return entry


def _settlement(trade_id: str = "TR-1") -> dict:
    """A trade settlement entry booked on 1 June, money out."""
    return _entry(entry_type="TRADE_SETTLEMENT", trade_id=trade_id,
                  debit=None, credit="4852.40")


TRADES = {"TR-1": {"trade_id": "TR-1", "trade_date": "2026-06-01",
                   "settlement_date": "2026-06-03"}}
PARTIES = {"PF-1": "Test Client"}
DOMICILES = {"ABC": "overseas"}


@pytest.fixture(scope="module")
def june_items():
    connector = JsonFirmConnector(JUNE_FIRM / "accounts.json", JUNE_FIRM / "portfolios.json")
    trades = {t["trade_id"]: t for t in connector.canonical["trades"]}
    parties = parties_by_portfolio(connector.canonical)
    domiciles = domiciles_by_ticker(connector.canonical)
    entries = connector.get_cash_entries("ACC-KRW-CASH-01", date(2026, 6, 1), date(2026, 6, 30))
    return {item["id"]: item
            for item in (firm_to_item(e, trades, parties, domiciles) for e in entries)}


# ---------------- 1. signed_amount ----------------

def test_debit_is_money_in_so_positive():
    assert signed_amount(_entry(debit="25000.00", credit=None)) == Decimal("25000.00")


def test_credit_is_money_out_so_negative():
    assert signed_amount(_entry(debit=None, credit="4852.40")) == Decimal("-4852.40")


def test_signed_amount_is_a_decimal_not_a_float():
    assert isinstance(signed_amount(_entry()), Decimal)


# ---------------- 2. expected_date ----------------

def test_settlement_is_expected_on_its_trades_settlement_date():
    # Booked on 1 June (trade date), the money moves on 3 June.
    assert expected_date(_settlement(), TRADES) == date(2026, 6, 3)


def test_other_entries_are_expected_on_their_own_date():
    assert expected_date(_entry(date="2026-06-22"), TRADES) == date(2026, 6, 22)


# ---------------- 3. missing trade ----------------

def test_settlement_with_missing_trade_raises_naming_the_entry():
    with pytest.raises(ValueError, match="CE-TEST-0001: trade 'TR-404' not found"):
        expected_date(_settlement(trade_id="TR-404"), TRADES)


# ---------------- other fields ----------------

def test_empty_reference_becomes_none():
    assert firm_to_item(_entry(reference=""), TRADES, PARTIES, DOMICILES)["reference"] is None


def test_party_is_the_client_behind_the_portfolio():
    assert firm_to_item(_entry(portfolio_id="PF-1"), TRADES, PARTIES, DOMICILES)["party"] == "Test Client"


def test_dividend_carries_its_securitys_domicile():
    entry = _entry(entry_type="DIVIDEND", ticker="ABC")
    assert firm_to_item(entry, TRADES, PARTIES, DOMICILES)["domicile"] == "overseas"


def test_entry_without_a_security_has_no_domicile():
    assert firm_to_item(_entry(ticker=None), TRADES, PARTIES, DOMICILES)["domicile"] is None


def test_account_entry_has_no_party():
    # Custody fees and interest belong to the account, not to a client.
    assert firm_to_item(_entry(portfolio_id=None), TRADES, PARTIES, DOMICILES)["party"] is None


# ---------------- 4. June: shape ----------------

def test_june_gives_sixteen_items_with_the_same_keys(june_items):
    assert len(june_items) == 16
    assert all(set(item) == ITEM_KEYS for item in june_items.values())
    assert all(item["side"] == "firm" for item in june_items.values())
    assert all(isinstance(item["amount"], Decimal) for item in june_items.values())
    assert all(isinstance(item["date"], date) for item in june_items.values())
    assert all(isinstance(item["expected_date"], date) for item in june_items.values())


# ---------------- 5. June: values ----------------

def test_june_settlement_is_prepared_correctly(june_items):
    assert june_items["CE-2026-06-0002"] == {
        "id": "CE-2026-06-0002",
        "side": "firm",
        "date": date(2026, 6, 1),
        "expected_date": date(2026, 6, 3),
        "amount": Decimal("-4852.40"),
        "reference": "TR-26060101",
        "entry_type": "TRADE_SETTLEMENT",
        "description": "Buy 400 ALBN",
        "party": "Amelia Hart",
        "domicile": None,
    }


def test_june_trade_settling_in_july_is_expected_in_july(june_items):
    assert june_items["CE-2026-06-0011"]["expected_date"] == date(2026, 7, 1)


def test_june_subscriptions_carry_their_clients_names(june_items):
    assert june_items["CE-2026-06-0007"]["party"] == "Priya Nair"
    assert june_items["CE-2026-06-0008"]["party"] == "Hart Family Trust"


def test_june_dividend_is_from_an_overseas_security(june_items):
    assert june_items["CE-2026-06-0004"]["domicile"] == "overseas"