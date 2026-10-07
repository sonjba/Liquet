from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest
import firm_connector
import re

ACCOUNT_LIST = Path(__file__).parent / "fixtures" / "2026-06" / "firm" / "accounts.json"

def test_account_return_a_list_of_1():
    account_list = firm_connector.load_json(ACCOUNT_LIST)
    assert account_list[0]["account_id"] == "ACC-KRW-CASH-01"

def test_missing_file_raises_file_not_found(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        firm_connector.load_json(missing)

def test_account_list_with_value_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a list"):
        firm_connector.load_json(bad)