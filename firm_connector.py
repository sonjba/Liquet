"""Read the firm's data and return it in Liquet's canonical shape.

Step 1: load one JSON file.
"""

from __future__ import annotations

import json
from pathlib import Path


# Liquet's name : the name in the FIRM'S database
ACCOUNT_FIELDS = {
    "account_id" :"account_id",
    "account_name" : "name",
    "currency" : "currency",
    "custodian" : "custodian",
}

# Liquet's name : the name in the FIRM'S database
ACCOUNT_BALANCE_FIELDS = {
    "as_of" : "as_of",
    "balance" : "balance",
}


def load_json(path: Path) -> list[dict]:
    """Read a JSON file that holds a list of records and return that list."""
    with open(path, "r", encoding="utf-8") as f:
        try:
            json_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"{path}: not valid JSON (line {e.lineno}): {e.msg}"
            ) from e

    if not isinstance(json_data, list):
        raise ValueError(
            f"{path}: expected a list of records, got {type(json_data).__name__}"
        )
    return json_data


def to_accounts(raw_accounts: list[dict]) -> list[dict]:
    """Convert the firm's account data to Liquet's canonical shape."""
    accounts = []
    for raw_account in raw_accounts:
        account_id = raw_account.get("account_id", "<unknown>")
        account = {}
        for liquet_field, firm_field in ACCOUNT_FIELDS.items():
            if firm_field not in raw_account:
                raise ValueError(f"Account {account_id}: missing field {firm_field!r}")
            account[liquet_field] = raw_account[firm_field]
        account["source"] = f"accounts/{account_id}"
        accounts.append(account)
    return accounts


def to_account_balances(raw_accounts: list[dict]) -> list[dict]:
    """Convert the balances nested inside the firm's accounts to Liquet's
    canonical `account_balances`: one flat list, one record per balance."""
    balances = []
    for raw_account in raw_accounts:
        account_id = raw_account.get("account_id", "<unknown>")
        for index, raw_balance in enumerate(raw_account.get("cash_balances", [])):
            balance = {"account_id": account_id}
            for liquet_field, firm_field in ACCOUNT_BALANCE_FIELDS.items():
                if firm_field not in raw_balance:
                    raise ValueError(
                        f"Account {account_id}, balance {index}: missing field {firm_field!r}"
                    )
                balance[liquet_field] = raw_balance[firm_field]
            balance["source"] = f"accounts/{account_id}/cash_balances/{index}"
            balances.append(balance)
    return balances



if __name__ == "__main__":
    raw_accounts = load_json(Path("tests/fixtures/2026-06/firm/accounts.json"))
    print(to_accounts(raw_accounts))
    print(to_account_balances(raw_accounts))