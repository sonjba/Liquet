from pathlib import Path

import pytest

import firm_connector

ACCOUNT_LIST = Path(__file__).parent / "fixtures" / "2026-06" / "firm" / "accounts.json"


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


# ---------------- boundaries ----------------

def test_empty_input_gives_empty_lists():
    assert firm_connector.to_accounts([]) == []
    assert firm_connector.to_account_balances([]) == []


def test_account_with_no_balances_gives_empty_list():
    raw_account = {"account_id": "X1", "cash_balances": []}
    assert firm_connector.to_account_balances([raw_account]) == []


def test_account_without_cash_balances_key_gives_empty_list():
    # Deliberate: no balances here is not an error at this stage.
    # Check 8 (an opening balance exists) catches a missing balance later.
    raw_account = {"account_id": "X1"}
    assert firm_connector.to_account_balances([raw_account]) == []


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


# ---------------- bad input ----------------

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

