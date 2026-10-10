from pathlib import Path

import pytest

import firm_connector

ACCOUNT_LIST = Path(__file__).parent / "fixtures" / "2026-06" / "firm" / "accounts.json"
PORTFOLIO_LIST = Path(__file__).parent / "fixtures" / "2026-06" / "firm" / "portfolios.json"


# ---------------- load_json ----------------

def test_load_json_reads_fixture():
    account_list = firm_connector.load_json(ACCOUNT_LIST)
    assert len(account_list) == 1
    assert account_list[0]["account_id"] == "ACC-KRW-CASH-01"


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


# ---------------- to_accounts / to_account_balances: normal case ----------------

def test_account_list_is_read_correctly():
    # Regression: an earlier version left out "source".
    accounts = firm_connector.to_accounts(firm_connector.load_json(ACCOUNT_LIST))
    assert accounts == [
        {
            "account_id": "ACC-KRW-CASH-01",
            "account_name": "Client cash account",
            "currency": "GBP",
            "custodian": "Northgate Custody Bank",
            "source": "accounts/ACC-KRW-CASH-01",
        }
    ]


def test_account_balances_are_read_correctly():
    # Regression: an earlier version read as_of and balance from the account
    # itself instead of from cash_balances, and had no account_id or source.
    balance_list = firm_connector.to_account_balances(firm_connector.load_json(ACCOUNT_LIST))
    assert balance_list == [
        {
            "account_id": "ACC-KRW-CASH-01",
            "as_of": "2026-05-31",
            "balance": "250000.00",
            "source": "accounts/ACC-KRW-CASH-01/cash_balances/0",
        }
    ]


def test_portfolios_are_read_correctly():
    portfolios = firm_connector.to_portfolios(firm_connector.load_json(PORTFOLIO_LIST))
    assert portfolios == [
        {"portfolio_id": f"PF-CL-00{n}",
         "account_id": "ACC-KRW-CASH-01",
         "client_id": f"CL-00{n}", 
         "source": f"portfolios/PF-CL-00{n}"}
        for n in range(1, 6)
    ]

def test_clients_are_read_correctly():
    clients = firm_connector.to_clients(firm_connector.load_json(PORTFOLIO_LIST))
    assert clients == [
    {"client_id": "CL-001", "name": "Amelia Hart",       "client_type": "individual", "source": "portfolios/PF-CL-001/client"},
    {"client_id": "CL-002", "name": "Daniel Okoro",      "client_type": "individual", "source": "portfolios/PF-CL-002/client"},
    {"client_id": "CL-003", "name": "Priya Nair",        "client_type": "individual", "source": "portfolios/PF-CL-003/client"},
    {"client_id": "CL-004", "name": "Thomas Reid",       "client_type": "individual", "source": "portfolios/PF-CL-004/client"},
    {"client_id": "CL-005", "name": "Hart Family Trust", "client_type": "trust",      "source": "portfolios/PF-CL-005/client"},
]

def _fixture_cash_book():
    return firm_connector.to_cash_book(
        firm_connector.load_json(ACCOUNT_LIST),
        firm_connector.load_json(PORTFOLIO_LIST),
    )


def test_cash_book_has_every_movement():
    # Regression: an earlier version never appended the portfolio movements,
    # so only the account movement came through.
    assert len(_fixture_cash_book()) == 17   # 16 June movements + 1 May interest


def test_cash_book_trade_entry_is_read_correctly():
    entries = {e["entry_id"]: e for e in _fixture_cash_book()}
    assert entries["CE-2026-06-0002"] == {
        "entry_id": "CE-2026-06-0002", "date": "2026-06-01", "recorded_at": "2026-06-01",
        "entry_type": "TRADE_SETTLEMENT", "description": "Buy 400 ALBN", "reference": "TR-26060101",
        "account_id": "ACC-KRW-CASH-01", "portfolio_id": "PF-CL-001", "trade_id": "TR-26060101",
        "ticker": None, "debit": None, "credit": "4852.40",
        "source": "portfolios/PF-CL-001/cash_movements/1",
    }

# ---------------- boundaries ----------------

def test_empty_input_gives_empty_lists():
    assert firm_connector.to_accounts([]) == []
    assert firm_connector.to_account_balances([]) == []
    assert firm_connector.to_portfolios([]) == []
    assert firm_connector.to_clients([]) == []


def test_account_with_no_balances_gives_empty_list():
    raw_account = {"account_id": "X1", "cash_balances": []}
    assert firm_connector.to_account_balances([raw_account]) == []


def test_account_without_cash_balances_key_gives_empty_list():
    # Deliberate: no balances here is not an error at this stage.
    # Check 8 (an opening balance exists) catches a missing balance later.
    raw_account = {"account_id": "X1"}
    assert firm_connector.to_account_balances([raw_account]) == []

def test_portfolio_without_client_raises():
    raw_portfolio = {"portfolio_id": "P1"}
    with pytest.raises(ValueError, match="missing or invalid 'client'"):
        firm_connector.to_clients([raw_portfolio])

def test_every_cash_entry_has_exactly_one_of_debit_or_credit():
    for e in _fixture_cash_book():
        assert (e["debit"] is None) != (e["credit"] is None), e["entry_id"]

def test_out_movement_goes_to_credit_only():
    portfolio = _raw_portfolio("P1", "C1")
    portfolio["cash_movements"] = [_raw_movement(direction="OUT", amount="50.00")]
    [entry] = firm_connector.to_cash_book([], [portfolio])
    assert entry["credit"] == "50.00"
    assert entry["debit"] is None

def test_account_movement_has_no_portfolio():
    entries = {e["entry_id"]: e for e in _fixture_cash_book()}
    interest = entries["CE-2026-05-0030"]
    assert interest["portfolio_id"] is None
    assert interest["source"].startswith("accounts/")


def test_empty_cash_book_inputs_give_empty_list():
    assert firm_connector.to_cash_book([], []) == []


def test_portfolio_without_cash_movements_gives_no_entries():
    assert firm_connector.to_cash_book([], [_raw_portfolio("P1", "C1")]) == []

# ---------------- silent wrong ----------------

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

def test_portfolios_keep_their_own_client_id():
    # Catches every portfolio taking the first portfolio's client_id.
    raw_portfolios = [_raw_portfolio("P1", "C1"), _raw_portfolio("P2", "C2")]
    portfolios = firm_connector.to_portfolios(raw_portfolios)
    assert [p["client_id"] for p in portfolios] == ["C1", "C2"]


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


# ---------------- bad input ----------------

@pytest.mark.parametrize("missing", ["portfolio_id", "custody_account"])
def test_portfolio_missing_field_raises(missing):
    raw = _raw_portfolio("P1", "C1")
    del raw[missing]
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_portfolios([raw])

@pytest.mark.parametrize("missing", ["account_id", "name", "currency", "custodian"])
def test_account_missing_field_raises(missing):
    raw = {"account_id": "X1", "name": "N", "currency": "GBP", "custodian": "C"}
    del raw[missing]
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_accounts([raw])


@pytest.mark.parametrize("missing", ["as_of", "balance"])
def test_balance_missing_field_raises(missing):
    entry = {"as_of": "2026-05-30", "balance": "50000.00"}
    del entry[missing]
    raw_account = {"account_id": "X1", "cash_balances": [entry]}
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_account_balances([raw_account])

@pytest.mark.parametrize("missing", ["client_id", "full_name", "type"])
def test_client_missing_field_raises(missing):
    raw = _raw_portfolio("P1", "C1")
    del raw["client"][missing]
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_clients([raw])

def test_portfolio_without_client_raises_in_to_portfolios():
    raw = _raw_portfolio("P1", "C1")
    del raw["client"]
    with pytest.raises(ValueError, match="client.client_id"):
        firm_connector.to_portfolios([raw])

def test_unknown_direction_raises():
    portfolio = _raw_portfolio("P1", "C1")
    portfolio["cash_movements"] = [_raw_movement(direction="SIDEWAYS")]
    with pytest.raises(ValueError, match="IN or OUT"):
        firm_connector.to_cash_book([], [portfolio])


@pytest.mark.parametrize("missing", ["movement_id", "value_date", "entered_on", "kind",
                                     "narrative", "our_ref", "direction", "amount"])
def test_movement_missing_field_raises(missing):
    movement = _raw_movement()
    del movement[missing]
    portfolio = _raw_portfolio("P1", "C1")
    portfolio["cash_movements"] = [movement]
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_cash_book([], [portfolio])


# ---------------- the path engine (_extract) ----------------
# These call _extract directly with small made-up mappings, so they test the
# path rules themselves, not the firm's mapping.

def test_optional_field_missing_gives_none():
    data = {"accounts": [{"account_id": "A1"}]}
    block = {"account_id": "accounts[*].account_id",
             "nickname": "accounts[*].details.nickname?"}
    assert firm_connector._extract(data, block) == [
        {"account_id": "A1", "nickname": None, "source": "accounts/A1"},
    ]


def test_required_field_missing_raises():
    data = {"accounts": [{"account_id": "A1"}]}
    block = {"account_id": "accounts[*].account_id",
             "nickname": "accounts[*].details.nickname"}
    with pytest.raises(ValueError, match="details.nickname"):
        firm_connector._extract(data, block)


def test_list_path_that_is_not_a_list_raises():
    data = {"accounts": [{"account_id": "A1", "cash_balances": {"as_of": "2026-05-31"}}]}
    block = {"as_of": "accounts[*].cash_balances[*].as_of"}
    with pytest.raises(ValueError, match="should be a list"):
        firm_connector._extract(data, block)


def test_three_levels_give_one_record_per_deepest_item():
    # 1 account -> 2 groups -> 2 + 1 items = 3 records, each with its parents' values.
    data = {"accounts": [{
        "account_id": "A1",
        "groups": [
            {"group": "G1", "items": [{"x": 1}, {"x": 2}]},
            {"group": "G2", "items": [{"x": 3}]},
        ],
    }]}
    block = {"account_id": "accounts[*].account_id",
             "group":      "accounts[*].groups[*].group",
             "x":          "accounts[*].groups[*].items[*].x"}
    assert firm_connector._extract(data, block) == [
        {"account_id": "A1", "group": "G1", "x": 1, "source": "accounts/A1/groups/0/items/0"},
        {"account_id": "A1", "group": "G1", "x": 2, "source": "accounts/A1/groups/0/items/1"},
        {"account_id": "A1", "group": "G2", "x": 3, "source": "accounts/A1/groups/1/items/0"},
    ]


def test_none_in_mapping_gives_none():
    data = {"accounts": [{"account_id": "A1"}]}
    block = {"account_id": "accounts[*].account_id", "portfolio_id": None}
    assert firm_connector._extract(data, block)[0]["portfolio_id"] is None


# ---------------- trades ----------------

PORTFOLIOS = PORTFOLIO_LIST   # same fixture, clearer name in these tests


def test_trades_one_per_trade_settlement():
    # 16 June movements, 5 of them trade settlements.
    assert len(firm_connector.to_trades(firm_connector.load_json(PORTFOLIOS))) == 5


def test_trade_is_read_correctly():
    trades = {t["trade_id"]: t for t in firm_connector.to_trades(firm_connector.load_json(PORTFOLIOS))}
    # The ALBN buy agreed 29 June that settles 1 July (B2 in the answer key).
    assert trades["TR-26062901"] == {
        "trade_id": "TR-26062901", "portfolio_id": "PF-CL-001", "account_id": "ACC-KRW-CASH-01",
        "ticker": "ALBN", "side": "BUY", "trade_date": "2026-06-29", "settlement_date": "2026-07-01",
        "quantity": 300, "price": "12.35", "costs": "12.00", "settlement_amount": "3717.00",
        "source": "portfolios/PF-CL-001/cash_movements/2/trade",
    }


def _raw_trade():
    return {"trade_ref": "T1", "side": "BUY", "trade_date": "2026-06-01",
            "settle_date": "2026-06-03", "qty": 10, "unit_price": "1.00",
            "fees": "0.50", "consideration": "10.50", "security": {"ticker": "XYZ"}}


@pytest.mark.parametrize("missing", ["trade_ref", "side", "trade_date", "settle_date",
                                     "qty", "unit_price", "fees", "consideration"])
def test_trade_missing_field_raises(missing):
    trade = _raw_trade()
    del trade[missing]
    portfolio = _raw_portfolio("P1", "C1")
    portfolio["cash_movements"] = [_raw_movement(trade=trade)]
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_trades([portfolio])


def test_no_trades_gives_empty_list():
    portfolio = _raw_portfolio("P1", "C1")
    portfolio["cash_movements"] = [_raw_movement()]   # a subscription, no trade
    assert firm_connector.to_trades([portfolio]) == []


# ---------------- the path engine: "b?" skips items without b ----------------

def test_optional_step_skips_items_without_it():
    data = {"accounts": [{"account_id": "A1", "items": [
        {"extra": {"x": 1}},
        {},                     # no "extra": skipped, not an error
        {"extra": {"x": 3}},
    ]}]}
    block = {"x": "accounts[*].items[*].extra?.x"}
    assert firm_connector._extract(data, block) == [
        {"x": 1, "source": "accounts/A1/items/0/extra"},
        {"x": 3, "source": "accounts/A1/items/2/extra"},
    ]


# ---------------- securities ----------------

def test_securities_one_per_ticker():
    # ALBN appears in three trades; it must come out once.
    securities = firm_connector.to_securities(firm_connector.load_json(PORTFOLIO_LIST))
    assert securities == [
        {"ticker": "ALBN", "name": "Albion Utilities plc", "security_type": "share",
         "domicile": "uk", "source": "portfolios/PF-CL-001/cash_movements/1/trade/security"},
        {"ticker": "THIX", "name": "Thames Index Fund", "security_type": "fund",
         "domicile": "uk", "source": "portfolios/PF-CL-002/cash_movements/0/trade/security"},
        {"ticker": "SEVN", "name": "Severn Pharma plc", "security_type": "share",
         "domicile": "uk", "source": "portfolios/PF-CL-003/cash_movements/0/trade/security"},
        {"ticker": "ATIT", "name": "Atlantic Income Trust", "security_type": "fund",
         "domicile": "overseas", "source": "portfolios/PF-CL-004/cash_movements/0/dividend/security"},
    ]


def _security(name="Xyz plc", domicile="uk"):
    return {"ticker": "XYZ", "name": name, "type": "share", "domicile": domicile}


def test_same_security_in_trade_and_dividend_gives_one_record():
    trade = _raw_trade()
    trade["security"] = _security()
    portfolio = _raw_portfolio("P1", "C1")
    portfolio["cash_movements"] = [
        _raw_movement("M1", trade=trade),
        _raw_movement("M2", dividend={"security": _security()}),
    ]
    assert [s["ticker"] for s in firm_connector.to_securities([portfolio])] == ["XYZ"]


def test_security_copies_that_disagree_raise():
    # Silent wrong otherwise: the domicile decides whether a dividend is taxed.
    trade = _raw_trade()
    trade["security"] = _security(domicile="uk")
    portfolio = _raw_portfolio("P1", "C1")
    portfolio["cash_movements"] = [
        _raw_movement("M1", trade=trade),
        _raw_movement("M2", dividend={"security": _security(domicile="overseas")}),
    ]
    with pytest.raises(ValueError, match="Security XYZ: details differ"):
        firm_connector.to_securities([portfolio])


@pytest.mark.parametrize("missing", ["ticker", "name", "type", "domicile"])
def test_security_missing_field_raises(missing):
    security = _security()
    del security[missing]
    portfolio = _raw_portfolio("P1", "C1")
    portfolio["cash_movements"] = [_raw_movement(dividend={"security": security})]
    with pytest.raises(ValueError, match=missing):
        firm_connector.to_securities([portfolio])


def test_no_trades_or_dividends_gives_no_securities():
    portfolio = _raw_portfolio("P1", "C1")
    portfolio["cash_movements"] = [_raw_movement()]
    assert firm_connector.to_securities([portfolio]) == []