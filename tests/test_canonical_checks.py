"""Tests for canonical_checks.py.

Each test takes a fresh copy of the real June output, breaks one thing,
and checks that the right check reports it, naming the record.
"""

import copy
from datetime import date

import pytest

import firm_connector
from canonical_checks import (
    CanonicalCheckError, check_canonical, check_cash_entries, check_ids_are_unique,
    check_money_is_text, check_opening_balance_exists, check_references_exist,
    check_settlements_match_trades, check_trades_add_up,
)

JUNE_START = date(2026, 6, 1)


@pytest.fixture(scope="module")
def june_output(june_accounts, june_portfolios):
    return firm_connector.to_canonical(june_accounts, june_portfolios)


@pytest.fixture
def june(june_output):
    """A copy of the June output that a test may change."""
    return copy.deepcopy(june_output)


def _find(records, field, value):
    [record] = [r for r in records if r[field] == value]
    return record


def _problems(error) -> str:
    return "\n".join(error.value.problems)


# ---------------- the June data passes ----------------

def test_june_passes_every_check(june):
    check_canonical(june, JUNE_START)   # raises if anything fails


def test_every_problem_is_listed_at_once(june):
    _find(june["trades"], "trade_id", "TR-26060101")["settlement_amount"] = "1.00"
    june["clients"].append(copy.deepcopy(june["clients"][0]))
    with pytest.raises(CanonicalCheckError) as error:
        check_canonical(june, JUNE_START)
    checks = [p.split(",")[0] for p in error.value.problems]
    assert "check 1" in checks and "check 3" in checks and "check 5" in checks


def test_missing_collection_raises(june):
    del june["trades"]
    with pytest.raises(CanonicalCheckError, match="missing collection.*trades"):
        check_canonical(june, JUNE_START)


# ---------------- check 1: ids are unique ----------------

def test_duplicate_entry_id_is_reported(june):
    copied = copy.deepcopy(june["cash_book"][0])
    copied["source"] = "portfolios/PF-CL-009/cash_movements/0"
    june["cash_book"].append(copied)
    [problem] = check_ids_are_unique(june)
    assert problem == ("check 1, cash_book CE-2026-06-0001 (portfolios/PF-CL-009/cash_movements/0): "
                       "same id as portfolios/PF-CL-001/cash_movements/0")


def test_balances_are_identified_by_account_and_date(june):
    # Two balances for one account on different dates are fine.
    later = dict(june["account_balances"][0], as_of="2026-06-30")
    june["account_balances"].append(later)
    assert check_ids_are_unique(june) == []


# ---------------- check 2: references exist ----------------

@pytest.mark.parametrize("collection, id_field, record_id, field", [
    ("portfolios", "portfolio_id", "PF-CL-001", "client_id"),
    ("portfolios", "portfolio_id", "PF-CL-001", "account_id"),
    ("trades", "trade_id", "TR-26060101", "ticker"),
    ("trades", "trade_id", "TR-26060101", "portfolio_id"),
    ("cash_book", "entry_id", "CE-2026-06-0002", "trade_id"),
    ("cash_book", "entry_id", "CE-2026-06-0004", "ticker"),
    ("account_balances", "account_id", "ACC-KRW-CASH-01", "account_id"),
])
def test_reference_to_nothing_is_reported(june, collection, id_field, record_id, field):
    _find(june[collection], id_field, record_id)[field] = "NOPE"
    problems = check_references_exist(june)
    assert any(p.startswith(f"check 2, {collection} ") and f"{field} 'NOPE' is not in" in p
               for p in problems), problems


def test_none_is_allowed_only_where_the_format_says_null(june):
    # trade_id None on a subscription is fine; client_id None on a portfolio is not.
    assert _find(june["cash_book"], "entry_id", "CE-2026-06-0001")["trade_id"] is None
    _find(june["portfolios"], "portfolio_id", "PF-CL-001")["client_id"] = None
    [problem] = check_references_exist(june)
    assert "client_id None is not in clients" in problem


# ---------------- check 3: trades add up ----------------

def test_trade_that_does_not_add_up_is_reported(june):
    # 400 x 12.10 + 12.40 = 4852.40
    _find(june["trades"], "trade_id", "TR-26060101")["settlement_amount"] = "4840.00"
    [problem] = check_trades_add_up(june)
    assert "settlement_amount 4840.00, expected 4852.40 (400 x 12.10 + 12.40)" in problem


def test_sell_subtracts_costs(june):
    # Silent wrong if costs were added for a sell too: 250 x 24.80 + 12.50 = 6212.50.
    _find(june["trades"], "trade_id", "TR-26060302")["settlement_amount"] = "6212.50"
    [problem] = check_trades_add_up(june)
    assert "expected 6187.50" in problem


@pytest.mark.parametrize("quantity", [0, -5, 2.5, "400", True, None])
def test_quantity_must_be_a_whole_number_above_zero(june, quantity):
    _find(june["trades"], "trade_id", "TR-26060101")["quantity"] = quantity
    [problem] = check_trades_add_up(june)
    assert "quantity must be a whole number above 0" in problem


def test_unknown_side_is_reported(june):
    _find(june["trades"], "trade_id", "TR-26060101")["side"] = "HOLD"
    [problem] = check_trades_add_up(june)
    assert "side must be BUY or SELL, got 'HOLD'" in problem


# ---------------- check 4: cash entries ----------------

@pytest.mark.parametrize("debit, credit", [(None, None), ("1.00", "1.00")])
def test_entry_needs_exactly_one_of_debit_or_credit(june, debit, credit):
    entry = _find(june["cash_book"], "entry_id", "CE-2026-06-0001")
    entry["debit"], entry["credit"] = debit, credit
    [problem] = check_cash_entries(june)
    assert "needs exactly one of debit or credit" in problem


@pytest.mark.parametrize("entry_id, field, value, message", [
    ("CE-2026-06-0001", "portfolio_id", None, "a SUBSCRIPTION entry needs a portfolio_id"),
    ("CE-2026-05-0030", "portfolio_id", "PF-CL-001", "a INTEREST entry belongs to no portfolio"),
    ("CE-2026-06-0002", "trade_id", None, "a TRADE_SETTLEMENT needs a trade_id"),
    ("CE-2026-06-0004", "ticker", None, "a DIVIDEND needs a ticker"),
    ("CE-2026-06-0001", "entry_type", "GIFT", "unknown entry_type 'GIFT'"),
])
def test_entry_links_must_fit_its_type(june, entry_id, field, value, message):
    _find(june["cash_book"], "entry_id", entry_id)[field] = value
    [problem] = check_cash_entries(june)
    assert problem.startswith(f"check 4, cash_book {entry_id} (")
    assert message in problem


# ---------------- check 5: settlements match their trade ----------------

def test_settlement_amount_must_match_its_trade(june):
    _find(june["cash_book"], "entry_id", "CE-2026-06-0002")["credit"] = "4852.04"
    [problem] = check_settlements_match_trades(june)
    assert "amount 4852.04, but trade TR-26060101 settles 4852.40" in problem


def test_buy_must_be_money_out(june):
    entry = _find(june["cash_book"], "entry_id", "CE-2026-06-0002")
    entry["debit"], entry["credit"] = entry["credit"], None
    [problem] = check_settlements_match_trades(june)
    assert "a BUY should be a credit" in problem


def test_settlement_must_be_for_the_trades_portfolio(june):
    _find(june["cash_book"], "entry_id", "CE-2026-06-0002")["portfolio_id"] = "PF-CL-002"
    [problem] = check_settlements_match_trades(june)
    assert "portfolio PF-CL-002, but trade TR-26060101 is for PF-CL-001" in problem


def test_trade_settling_next_month_still_matches(june):
    # TR-26062901 settles 1 July; its June entry must still pass.
    assert _find(june["trades"], "trade_id", "TR-26062901")["settlement_date"] == "2026-07-01"
    assert check_settlements_match_trades(june) == []


# ---------------- check 6: money is text ----------------

@pytest.mark.parametrize("value", [100.1, 1500.25, 250000, "100.1", "100", "1,000.00", "£5.00", "-5.00", "1e3"])
def test_bad_money_is_reported(june, value):
    _find(june["cash_book"], "entry_id", "CE-2026-06-0001")["debit"] = value
    [problem] = check_money_is_text(june)
    assert f"debit must be text with two decimals, got {value!r}" in problem


def test_float_money_stops_before_the_arithmetic(june):
    # The gap from the connector review: a JSON number gets through the
    # connector as a float. Here it stops the run, and checks 3 and 5 don't run on it.
    _find(june["trades"], "trade_id", "TR-26060101")["settlement_amount"] = 4852.4
    with pytest.raises(CanonicalCheckError) as error:
        check_canonical(june, JUNE_START)
    assert error.value.problems == [
        "check 6, trades TR-26060101 (portfolios/PF-CL-001/cash_movements/1/trade): "
        "settlement_amount must be text with two decimals, got 4852.4"]


def test_balance_may_be_negative(june):
    june["account_balances"][0]["balance"] = "-50.00"
    assert check_money_is_text(june) == []


# ---------------- check 8: an opening balance exists ----------------

def test_opening_balance_is_the_day_before_the_period(june):
    assert check_opening_balance_exists(june, date(2026, 6, 1)) == []
    [problem] = check_opening_balance_exists(june, date(2026, 7, 1))
    assert problem == ("check 8, accounts ACC-KRW-CASH-01 (accounts/ACC-KRW-CASH-01): "
                       "no opening balance as of 2026-06-30")


def test_no_balances_at_all_is_reported(june):
    june["account_balances"] = []
    with pytest.raises(CanonicalCheckError, match="no opening balance as of 2026-05-31"):
        check_canonical(june, JUNE_START)