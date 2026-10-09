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
    with pytest.raises(ValueError, match="missing client"):
        firm_connector.to_portfolios([raw])