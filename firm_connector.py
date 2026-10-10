"""Read the firm's data and return it in Liquet's canonical shape.

Done so far: accounts, recorded balances, portfolios, clients and the cash book.
Field names come from firm_mapping.py; _map_fields does the renaming and the
missing-field checks for every collection.
"""

from __future__ import annotations

import json
from pathlib import Path

from firm_mapping import FIRM_MAPPING


# Liquet's name : the name in the FIRM'S database
ACCOUNT_FIELDS = FIRM_MAPPING["accounts"]
ACCOUNT_BALANCE_FIELDS = FIRM_MAPPING["account_balances"]
PORTFOLIO_FIELDS = FIRM_MAPPING["portfolios"]
CLIENT_FIELDS = FIRM_MAPPING["clients"]
CASH_BOOK_FIELDS = FIRM_MAPPING["cash_book"]


def _map_fields(raw: dict, fields: dict, where: str, also_required: tuple = ()) -> dict:
    """Copy fields from one firm record into a new dict with Liquet's names.

    Stops with a clear error if any mapped field, or any field in
    also_required (needed by the caller's own logic), is missing."""
    for firm_field in [*fields.values(), *also_required]:
        if firm_field not in raw:
            raise ValueError(f"{where}: missing field {firm_field!r}")
    return {liquet_field: raw[firm_field] for liquet_field, firm_field in fields.items()}


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
        account = _map_fields(raw_account, ACCOUNT_FIELDS, f"Account {account_id}")
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
            balance |= _map_fields(raw_balance, ACCOUNT_BALANCE_FIELDS,
                                   f"Account {account_id}, balance {index}")
            balance["source"] = f"accounts/{account_id}/cash_balances/{index}"
            balances.append(balance)
    return balances

def to_portfolios(raw_portfolios: list[dict]) -> list[dict]:
    """Convert the firm's portfolios to Liquet's canonical `portfolios`, one
    record per portfolio, with the owner's client_id taken from the embedded client."""
    portfolios = []
    for raw_portfolio in raw_portfolios:
        portfolio_id = raw_portfolio.get("portfolio_id", "<unknown>")
        portfolio = {}

        client = raw_portfolio.get("client")
        if not isinstance(client, dict) or "client_id" not in client:
            raise ValueError(f"Portfolio {portfolio_id}: missing client or client_id")
        portfolio["client_id"] = client["client_id"]

        portfolio |= _map_fields(raw_portfolio, PORTFOLIO_FIELDS, f"Portfolio {portfolio_id}")
        portfolio["source"] = f"portfolios/{portfolio_id}"
        portfolios.append(portfolio)
    return portfolios


def to_clients(raw_portfolios: list[dict]) -> list[dict]:
    """Convert the clients embedded in the firm's portfolios to Liquet's
    canonical `clients`: one record per client, even when a client owns
    several portfolios."""
    clients_by_id = {}   # client_id -> (client, portfolio it was first read from)
    for raw_portfolio in raw_portfolios:
        portfolio_id = raw_portfolio.get("portfolio_id", "<unknown>")
        raw_client = raw_portfolio.get("client")
        if not isinstance(raw_client, dict):
            raise ValueError(f"Portfolio {portfolio_id}: missing or invalid 'client'")

        client = _map_fields(raw_client, CLIENT_FIELDS, f"Portfolio {portfolio_id}, client")

        client_id = client["client_id"]
        if client_id in clients_by_id:
            first, first_portfolio = clients_by_id[client_id]
            if first != client:
                raise ValueError(
                    f"Client {client_id}: details differ between portfolios "
                    f"{first_portfolio} and {portfolio_id}")
            continue   # same client, already recorded

        clients_by_id[client_id] = (client, portfolio_id)

    clients = []
    for client, portfolio_id in clients_by_id.values():
        client["source"] = f"portfolios/{portfolio_id}/client"
        clients.append(client)
    return clients


def _to_cash_entry(raw_movement: dict, account_id: str, portfolio_id: str | None, source: str) -> dict:
    """Convert one firm movement to one canonical cash_book entry."""
    entry_id = raw_movement.get("movement_id", "<unknown>")
    entry = _map_fields(raw_movement, CASH_BOOK_FIELDS, f"Cash movement {entry_id} ({source})",
                        also_required=("direction", "amount"))
    
    # fields added in code,because they are not present in the firm's cash_movement list data:
    entry["account_id"] = account_id
    entry["portfolio_id"] = portfolio_id

    trade = raw_movement.get("trade")
    entry["trade_id"] = trade["trade_ref"] if trade else None

    dividend = raw_movement.get("dividend")
    entry["ticker"] = dividend["security"]["ticker"] if dividend else None

    direction = raw_movement["direction"]
    if direction == "IN":
        entry["debit"], entry["credit"] = raw_movement["amount"], None
    elif direction == "OUT":
        entry["debit"], entry["credit"] = None, raw_movement["amount"]
    else:
        raise ValueError(f"Cash movement {entry_id}: direction must be IN or OUT, got {direction!r}")

    entry["source"] = source
    return entry


def to_cash_book(raw_accounts: list[dict], raw_portfolios: list[dict]) -> list[dict]:
    """Convert the firm's cash movements to Liquet's canonical `cash_book`:
    client movements from each portfolio, then account movements (fees,
    interest) that belong to no client."""
    entries = []
    for portfolio in raw_portfolios:
        portfolio_id = portfolio.get("portfolio_id", "<unknown>")
        account_id = portfolio.get("custody_account", "<unknown>")
        for index, movement in enumerate(portfolio.get("cash_movements", [])):
            source = f"portfolios/{portfolio_id}/cash_movements/{index}"
            entries.append(_to_cash_entry(movement, account_id, portfolio_id, source))

    for account in raw_accounts:
        account_id = account.get("account_id", "<unknown>")
        for index, movement in enumerate(account.get("account_movements", [])):
            source = f"accounts/{account_id}/account_movements/{index}"
            entries.append(_to_cash_entry(movement, account_id, None, source))
    return entries


if __name__ == "__main__":
    raw_accounts = load_json(Path("tests/fixtures/2026-06/firm/accounts.json"))
    raw_portfolios = load_json(Path("tests/fixtures/2026-06/firm/portfolios.json"))
    print(to_accounts(raw_accounts))
    print(to_account_balances(raw_accounts))
    print(to_portfolios(raw_portfolios))
    print(to_clients(raw_portfolios))
    cash_book = to_cash_book(raw_accounts, raw_portfolios)
    print(len(cash_book))   # expect 17
    print(cash_book[1])     # CE-2026-06-0002: trade_id TR-26060101, credit 4852.40