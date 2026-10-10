"""Tests for firm_connector.py: the firm's mapping and Liquet's own rules.

The path rules on their own are tested in test_path_mapper.py. The June
files are read once, in conftest.py.

After the first sections (the mapping, load_json, the whole June output)
there is one section per canonical collection, in this order:
normal case, boundaries, silent wrong, bad input. A regression test says
which earlier mistake it catches.
"""

import json
from pathlib import Path

import pytest

import firm_connector
from firm_mapping import FIRM_MAPPING, FIRM_RECORD_IDS
from path_mapper import check_mapping

EXPECTED = Path(__file__).parent / "fixtures" / "2026-06" / "expected" / "firm_canonical.json"

COLLECTIONS = ["accounts", "account_balances", "clients", "portfolios",
               "securities", "trades", "cash_book"]


# ---------------- small made-up firm records, one case at a time ----------------

def _raw_portfolio(portfolio_id, client_id, full_name="Some Name"):
    return {
        "portfolio_id": portfolio_id,
        "custody_account": "ACC-1",
        "client": {"client_id": client_id, "full_name": full_name, "type": "individual"},
    }


def _raw_movement(movement_id="M1", direction="IN", amount="100.00", **extra):
    movement = {
        "movement_id": movement_id, "value_date": "2026-06-01", "entered_on": "2026-06-01",
        "kind": "SUBSCRIPTION", "narrative": "Test", "our_ref": "REF-1",
        "direction": direction, "amount": amount,
    }
    movement.update(extra)   # e.g. trade={...} or dividend={...}
    return movement


def _portfolio_with(*movements):
    """Portfolio P1 (client C1) holding the given movements."""
    portfolio = _raw_portfolio("P1", "C1")
    portfolio["cash_movements"] = list(movements)
    return portfolio


def _raw_trade():
    return {"trade_ref": "T1", "side": "BUY", "trade_date": "2026-06-01",
            "settle_date": "2026-06-03", "qty": 10, "unit_price": "1.00",
            "fees": "0.50", "consideration": "10.50", "security": {"ticker": "XYZ"}}


def _raw_security(name="Xyz plc", domicile="uk"):
    return {"ticker": "XYZ", "name": name, "type": "share", "domicile": domicile}


# ---------------- the mapping ----------------

def test_firm_mapping_is_valid():
    # firm_connector also runs this when it is imported; this test makes a
    # broken line show up by name in the test results.
    check_mapping(FIRM_MAPPING, FIRM_RECORD_IDS)


def test_every_mapped_collection_is_in_the_output():
    assert sorted(FIRM_MAPPING) == sorted(COLLECTIONS)


# ---------------- load_json ----------------

def test_load_json_reads_fixture(june_accounts):
    assert len(june_accounts) == 1
    assert june_accounts[0]["account_id"] == "ACC-KRW-CASH-01"


def test_missing_file_raises_file_not_found(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        firm_connector.load_json(missing)


def test_not_a_list_raises_value_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a list"):
        firm_connector.load_json(bad)


def test_invalid_json_raises_value_error(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        firm_connector.load_json(bad)


# ---------------- the whole June output (golden file) ----------------
# tests/fixtures/2026-06/expected/firm_canonical.json holds the full canonical
# output for June, checked by eye. Any change to the output fails here, so a
# refactor can't change it without anyone noticing.
#
# After a change you mean to make (a new field, say), rewrite the file with
#     pytest --update-expected
# and read the change with git diff before committing it.

@pytest.fixture(scope="module")
def june_output(june_accounts, june_portfolios):
    return firm_connector.to_canonical(june_accounts, june_portfolios)


@pytest.fixture(scope="module")
def expected_output(request, june_output):
    if request.config.getoption("--update-expected"):
        # newline="\n": the same file whether it is written on Windows or a Mac
        with open(EXPECTED, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(june_output, indent=2, ensure_ascii=False) + "\n")
    with open(EXPECTED, encoding="utf-8") as f:
        return json.load(f)


def test_june_output_has_every_collection(june_output, expected_output):
    assert list(june_output) == COLLECTIONS
    assert list(expected_output) == COLLECTIONS


@pytest.mark.parametrize("collection", COLLECTIONS)
def test_june_output_matches_expected(collection, june_output, expected_output):
    assert june_output[collection] == expected_output[collection]


def test_empty_input_gives_empty_collections():
    assert firm_connector.to_canonical([], []) == {c: [] for c in COLLECTIONS}


# ---------------- accounts ----------------

def test_account_list_is_read_correctly(june_accounts):
    # Regression: an earlier version left out "source".
    assert firm_connector.to_accounts(june_accounts) == [
        {
            "account_id": "ACC-KRW-CASH-01",
            "account_name": "Client cash account",
            "currency": "GBP",
            "custodian": "Northgate Custody Bank",
            "source": "accounts/ACC-KRW-CASH-01",
        }
    ]


@pytest.mark.parametrize("missing", ["account_id", "name", "currency", "custodian"])
def test_account_missing_field_raises(missing):
    raw = {"account_id": "X1", "name": "N", "currency": "GBP", "custodian": "C"}
    del raw[missing]
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_accounts([raw])


# ---------------- account balances ----------------

def test_account_balances_are_read_correctly(june_accounts):
    # Regression: an earlier version read as_of and balance from the account
    # itself instead of from cash_balances, and had no account_id or source.
    assert firm_connector.to_account_balances(june_accounts) == [
        {
            "account_id": "ACC-KRW-CASH-01",
            "as_of": "2026-05-31",
            "balance": "250000.00",
            "source": "accounts/ACC-KRW-CASH-01/cash_balances/0",
        }
    ]


def test_account_with_no_balances_gives_empty_list():
    raw_account = {"account_id": "X1", "cash_balances": []}
    assert firm_connector.to_account_balances([raw_account]) == []


def test_account_without_cash_balances_list_raises():
    # Silent wrong before: a missing (or renamed) list gave no balances and
    # no error. The firm's accounts always have the list, even if empty.
    raw_account = {"account_id": "X1"}
    with pytest.raises(ValueError, match="accounts/X1: missing 'cash_balances'"):
        firm_connector.to_account_balances([raw_account])


def test_balances_keep_their_own_account_and_index():
    # The fixture has one account with one balance, so it cannot catch a
    # balance taking another account's id, or the index running 0,1,2,3
    # across accounts instead of 0,1 within each.
    raw_accounts = [
        {
            "account_id": "A1",
            "cash_balances": [
                {"as_of": "2026-04-30", "balance": "100.00"},
                {"as_of": "2026-05-31", "balance": "200.00"},
            ],
        },
        {
            "account_id": "A2",
            "cash_balances": [
                {"as_of": "2026-04-30", "balance": "300.00"},
                {"as_of": "2026-05-31", "balance": "-50.00"},
            ],
        },
    ]
    assert firm_connector.to_account_balances(raw_accounts) == [
        {"account_id": "A1", "as_of": "2026-04-30", "balance": "100.00", "source": "accounts/A1/cash_balances/0"},
        {"account_id": "A1", "as_of": "2026-05-31", "balance": "200.00", "source": "accounts/A1/cash_balances/1"},
        {"account_id": "A2", "as_of": "2026-04-30", "balance": "300.00", "source": "accounts/A2/cash_balances/0"},
        {"account_id": "A2", "as_of": "2026-05-31", "balance": "-50.00", "source": "accounts/A2/cash_balances/1"},
    ]


@pytest.mark.parametrize("missing", ["as_of", "balance"])
def test_balance_missing_field_raises(missing):
    entry = {"as_of": "2026-05-30", "balance": "50000.00"}
    del entry[missing]
    raw_account = {"account_id": "X1", "cash_balances": [entry]}
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_account_balances([raw_account])


def test_balance_that_is_null_raises():
    # Silent wrong before: the balance came through as None.
    raw_account = {"account_id": "X1", "cash_balances": [{"as_of": "2026-05-31", "balance": None}]}
    with pytest.raises(ValueError, match="missing 'balance'"):
        firm_connector.to_account_balances([raw_account])


# ---------------- clients ----------------

def test_clients_are_read_correctly(june_portfolios):
    assert firm_connector.to_clients(june_portfolios) == [
        {"client_id": "CL-001", "name": "Amelia Hart",       "client_type": "individual", "source": "portfolios/PF-CL-001/client"},
        {"client_id": "CL-002", "name": "Daniel Okoro",      "client_type": "individual", "source": "portfolios/PF-CL-002/client"},
        {"client_id": "CL-003", "name": "Priya Nair",        "client_type": "individual", "source": "portfolios/PF-CL-003/client"},
        {"client_id": "CL-004", "name": "Thomas Reid",       "client_type": "individual", "source": "portfolios/PF-CL-004/client"},
        {"client_id": "CL-005", "name": "Hart Family Trust", "client_type": "trust",      "source": "portfolios/PF-CL-005/client"},
    ]


def test_same_client_in_two_portfolios_gives_one_record():
    raw_portfolios = [
        _raw_portfolio("P1", "C1", "Amelia Hart"),
        _raw_portfolio("P2", "C1", "Amelia Hart"),
    ]
    assert firm_connector.to_clients(raw_portfolios) == [
        {"client_id": "C1", "name": "Amelia Hart", "client_type": "individual",
         "source": "portfolios/P1/client"},
    ]


def test_same_client_id_with_different_details_raises():
    raw_portfolios = [
        _raw_portfolio("P1", "C1", "Amelia Hart"),
        _raw_portfolio("P2", "C1", "Amelia Hartley"),
    ]
    with pytest.raises(ValueError, match="details differ"):
        firm_connector.to_clients(raw_portfolios)


def test_portfolio_without_client_raises():
    raw_portfolio = {"portfolio_id": "P1"}
    with pytest.raises(ValueError, match="portfolios/P1: missing 'client'"):
        firm_connector.to_clients([raw_portfolio])


@pytest.mark.parametrize("missing", ["client_id", "full_name", "type"])
def test_client_missing_field_raises(missing):
    raw = _raw_portfolio("P1", "C1")
    del raw["client"][missing]
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_clients([raw])


# ---------------- portfolios ----------------

def test_portfolios_are_read_correctly(june_portfolios):
    assert firm_connector.to_portfolios(june_portfolios) == [
        {"portfolio_id": f"PF-CL-00{n}",
         "account_id": "ACC-KRW-CASH-01",
         "client_id": f"CL-00{n}",
         "source": f"portfolios/PF-CL-00{n}"}
        for n in range(1, 6)
    ]


def test_portfolios_keep_their_own_client_id():
    # Catches every portfolio taking the first portfolio's client_id.
    raw_portfolios = [_raw_portfolio("P1", "C1"), _raw_portfolio("P2", "C2")]
    portfolios = firm_connector.to_portfolios(raw_portfolios)
    assert [p["client_id"] for p in portfolios] == ["C1", "C2"]


@pytest.mark.parametrize("missing", ["portfolio_id", "custody_account"])
def test_portfolio_missing_field_raises(missing):
    raw = _raw_portfolio("P1", "C1")
    del raw[missing]
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_portfolios([raw])


def test_portfolio_without_client_raises_in_to_portfolios():
    raw = _raw_portfolio("P1", "C1")
    del raw["client"]
    with pytest.raises(ValueError, match="missing 'client'"):
        firm_connector.to_portfolios([raw])


# ---------------- securities ----------------

def test_securities_one_per_ticker(june_portfolios):
    # ALBN appears in three trades; it must come out once.
    assert firm_connector.to_securities(june_portfolios) == [
        {"ticker": "ALBN", "name": "Albion Utilities plc", "security_type": "share",
         "domicile": "uk", "source": "portfolios/PF-CL-001/cash_movements/1/trade/security"},
        {"ticker": "THIX", "name": "Thames Index Fund", "security_type": "fund",
         "domicile": "uk", "source": "portfolios/PF-CL-002/cash_movements/0/trade/security"},
        {"ticker": "SEVN", "name": "Severn Pharma plc", "security_type": "share",
         "domicile": "uk", "source": "portfolios/PF-CL-003/cash_movements/0/trade/security"},
        {"ticker": "ATIT", "name": "Atlantic Income Trust", "security_type": "fund",
         "domicile": "overseas", "source": "portfolios/PF-CL-004/cash_movements/0/dividend/security"},
    ]


def test_no_trades_or_dividends_gives_no_securities():
    assert firm_connector.to_securities([_portfolio_with(_raw_movement())]) == []


def test_same_security_in_trade_and_dividend_gives_one_record():
    trade = _raw_trade()
    trade["security"] = _raw_security()
    portfolio = _portfolio_with(
        _raw_movement("M1", trade=trade),
        _raw_movement("M2", dividend={"security": _raw_security()}),
    )
    assert [s["ticker"] for s in firm_connector.to_securities([portfolio])] == ["XYZ"]


def test_security_copies_that_disagree_raise():
    # Silent wrong otherwise: the domicile decides whether a dividend is taxed.
    trade = _raw_trade()
    trade["security"] = _raw_security(domicile="uk")
    portfolio = _portfolio_with(
        _raw_movement("M1", trade=trade),
        _raw_movement("M2", dividend={"security": _raw_security(domicile="overseas")}),
    )
    with pytest.raises(ValueError, match="Security XYZ: details differ"):
        firm_connector.to_securities([portfolio])


@pytest.mark.parametrize("missing", ["ticker", "name", "type", "domicile"])
def test_security_missing_field_raises(missing):
    security = _raw_security()
    del security[missing]
    portfolio = _portfolio_with(_raw_movement(dividend={"security": security}))
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_securities([portfolio])


def test_dividend_without_security_raises_in_securities():
    portfolio = _portfolio_with(_raw_movement(dividend={}))
    with pytest.raises(ValueError, match="missing 'security'"):
        firm_connector.to_securities([portfolio])


# ---------------- trades ----------------

def test_trades_one_per_trade_settlement(june_portfolios):
    # 16 June movements, 5 of them trade settlements.
    assert len(firm_connector.to_trades(june_portfolios)) == 5


def test_trade_is_read_correctly(june_portfolios):
    trades = {t["trade_id"]: t for t in firm_connector.to_trades(june_portfolios)}
    # The ALBN buy agreed 29 June that settles 1 July (B2 in the answer key).
    assert trades["TR-26062901"] == {
        "trade_id": "TR-26062901", "portfolio_id": "PF-CL-001", "account_id": "ACC-KRW-CASH-01",
        "ticker": "ALBN", "side": "BUY", "trade_date": "2026-06-29", "settlement_date": "2026-07-01",
        "quantity": 300, "price": "12.35", "costs": "12.00", "settlement_amount": "3717.00",
        "source": "portfolios/PF-CL-001/cash_movements/2/trade",
    }


def test_no_trades_gives_empty_list():
    portfolio = _portfolio_with(_raw_movement())   # a subscription, no trade
    assert firm_connector.to_trades([portfolio]) == []


def test_trade_that_is_not_an_object_raises():
    # Silent wrong before: the movement was skipped as if it had no trade.
    portfolio = _portfolio_with(_raw_movement(trade="T1"))
    with pytest.raises(ValueError, match="'trade' should be an object, got str"):
        firm_connector.to_trades([portfolio])


@pytest.mark.parametrize("missing", ["trade_ref", "side", "trade_date", "settle_date",
                                     "qty", "unit_price", "fees", "consideration"])
def test_trade_missing_field_raises(missing):
    trade = _raw_trade()
    del trade[missing]
    portfolio = _portfolio_with(_raw_movement(trade=trade))
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_trades([portfolio])


# ---------------- cash book ----------------

@pytest.fixture(scope="module")
def june_cash_book(june_accounts, june_portfolios):
    return firm_connector.to_cash_book(june_accounts, june_portfolios)


def test_cash_book_has_every_movement(june_cash_book):
    # Regression: an earlier version never appended the portfolio movements,
    # so only the account movement came through.
    assert len(june_cash_book) == 17   # 16 June movements + 1 May interest


def test_cash_book_trade_entry_is_read_correctly(june_cash_book):
    entries = {e["entry_id"]: e for e in june_cash_book}
    assert entries["CE-2026-06-0002"] == {
        "entry_id": "CE-2026-06-0002", "date": "2026-06-01", "recorded_at": "2026-06-01",
        "entry_type": "TRADE_SETTLEMENT", "description": "Buy 400 ALBN", "reference": "TR-26060101",
        "account_id": "ACC-KRW-CASH-01", "portfolio_id": "PF-CL-001", "trade_id": "TR-26060101",
        "ticker": None, "debit": None, "credit": "4852.40",
        "source": "portfolios/PF-CL-001/cash_movements/1",
    }


def test_cash_book_dividend_entry_is_read_correctly(june_cash_book):
    entries = {e["entry_id"]: e for e in june_cash_book}
    assert entries["CE-2026-06-0004"] == {
        "entry_id": "CE-2026-06-0004", "date": "2026-06-10", "recorded_at": "2026-06-10",
        "entry_type": "DIVIDEND", "description": "Dividend ATIT", "reference": "DIV-ATIT-0610",
        "account_id": "ACC-KRW-CASH-01", "portfolio_id": "PF-CL-004", "trade_id": None,
        "ticker": "ATIT", "debit": "1500.00", "credit": None,
        "source": "portfolios/PF-CL-004/cash_movements/0",
    }


def test_every_cash_entry_has_exactly_one_of_debit_or_credit(june_cash_book):
    for e in june_cash_book:
        assert (e["debit"] is None) != (e["credit"] is None), e["entry_id"]


def test_out_movement_goes_to_credit_only():
    portfolio = _portfolio_with(_raw_movement(direction="OUT", amount="50.00"))
    [entry] = firm_connector.to_cash_book([], [portfolio])
    assert entry["credit"] == "50.00"
    assert entry["debit"] is None


def test_account_movement_has_no_portfolio(june_cash_book):
    entries = {e["entry_id"]: e for e in june_cash_book}
    interest = entries["CE-2026-05-0030"]
    assert interest["portfolio_id"] is None
    assert interest["source"].startswith("accounts/")


def test_empty_cash_book_inputs_give_empty_list():
    assert firm_connector.to_cash_book([], []) == []


def test_portfolio_without_cash_movements_gives_no_entries():
    assert firm_connector.to_cash_book([], [_portfolio_with()]) == []


def test_portfolio_without_cash_movements_list_raises():
    # Silent wrong before: if the firm renamed cash_movements, the June cash
    # book came out with 1 entry instead of 17, and nothing stopped.
    with pytest.raises(ValueError, match="portfolios/P1: missing 'cash_movements'"):
        firm_connector.to_cash_book([], [_raw_portfolio("P1", "C1")])


def test_dividend_without_security_raises():
    # Silent wrong before: the entry came out with ticker None and nothing
    # stopped, though a dividend must name its security.
    portfolio = _portfolio_with(_raw_movement(kind="DIVIDEND", dividend={}))
    with pytest.raises(ValueError, match="missing 'dividend.security'"):
        firm_connector.to_cash_book([], [portfolio])


def test_trade_without_trade_ref_raises_in_cash_book():
    # Silent wrong before: the entry came out with trade_id None.
    trade = _raw_trade()
    del trade["trade_ref"]
    portfolio = _portfolio_with(_raw_movement(kind="TRADE_SETTLEMENT", trade=trade))
    with pytest.raises(ValueError, match="missing 'trade.trade_ref'"):
        firm_connector.to_cash_book([], [portfolio])


def test_unknown_direction_raises():
    portfolio = _portfolio_with(_raw_movement(direction="SIDEWAYS"))
    with pytest.raises(ValueError, match="IN or OUT"):
        firm_connector.to_cash_book([], [portfolio])


@pytest.mark.parametrize("missing", ["movement_id", "value_date", "entered_on", "kind",
                                     "narrative", "our_ref", "direction", "amount"])
def test_movement_missing_field_raises(missing):
    movement = _raw_movement()
    del movement[missing]
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_cash_book([], [_portfolio_with(movement)])