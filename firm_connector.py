"""Read the firm's data and return it in Liquet's canonical shape.

Where each field comes from is written in firm_mapping.py as a path, for
example "accounts[*].cash_balances[*].balance", and path_mapper.py follows
the paths. This file never names a firm field itself. It adds Liquet's own
rules on top:
  - the firm's direction code decides debit or credit (cash book);
  - a client or security copied into several places becomes one record,
    and the copies must agree (canonical check 7).
"""

from __future__ import annotations

import json
from pathlib import Path

from firm_mapping import FIRM_DIRECTION_CODES, FIRM_MAPPING, FIRM_RECORD_IDS
from path_mapper import check_mapping, extract

# A mistake in firm_mapping.py stops everything here, before any data is read.
check_mapping(FIRM_MAPPING, FIRM_RECORD_IDS)


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


def to_canonical(raw_accounts: list[dict], raw_portfolios: list[dict]) -> dict[str, list[dict]]:
    """Everything Liquet needs from the firm, as canonical collections."""
    return {
        "accounts": to_accounts(raw_accounts),
        "account_balances": to_account_balances(raw_accounts),
        "clients": to_clients(raw_portfolios),
        "portfolios": to_portfolios(raw_portfolios),
        "securities": to_securities(raw_portfolios),
        "trades": to_trades(raw_portfolios),
        "cash_book": to_cash_book(raw_accounts, raw_portfolios),
    }


def _extract(collection: str, **datasets: list[dict]) -> list[dict]:
    """Records for one canonical collection, by its paths in firm_mapping.py.

    _extract("accounts", accounts=raw_accounts)
    """
    return extract(FIRM_MAPPING[collection], datasets, FIRM_RECORD_IDS, name=collection)


# ---------------- one function per canonical collection ----------------

def to_accounts(raw_accounts: list[dict]) -> list[dict]:
    """Convert the firm's accounts to Liquet's canonical `accounts`."""
    return _extract("accounts", accounts=raw_accounts)


def to_account_balances(raw_accounts: list[dict]) -> list[dict]:
    """Convert the balances inside the firm's accounts to Liquet's canonical
    `account_balances`: one record per balance, with its account's id."""
    return _extract("account_balances", accounts=raw_accounts)


def to_clients(raw_portfolios: list[dict]) -> list[dict]:
    """Convert the clients embedded in the firm's portfolios to Liquet's
    canonical `clients`: one record per client, even when a client owns
    several portfolios."""
    return _one_per_id(_extract("clients", portfolios=raw_portfolios), "client_id", "Client")


def to_portfolios(raw_portfolios: list[dict]) -> list[dict]:
    """Convert the firm's portfolios to Liquet's canonical `portfolios`."""
    return _extract("portfolios", portfolios=raw_portfolios)


def to_securities(raw_portfolios: list[dict]) -> list[dict]:
    """Convert the securities copied inside the firm's trades and dividends to
    Liquet's canonical `securities`: one record per ticker."""
    return _one_per_id(_extract("securities", portfolios=raw_portfolios), "ticker", "Security")


def to_trades(raw_portfolios: list[dict]) -> list[dict]:
    """Convert the trades inside the firm's trade-settlement movements to
    Liquet's canonical `trades`: one record per movement that has a trade."""
    return _extract("trades", portfolios=raw_portfolios)


def to_cash_book(raw_accounts: list[dict], raw_portfolios: list[dict]) -> list[dict]:
    """Convert the firm's cash movements to Liquet's canonical `cash_book`:
    client movements from each portfolio, then account movements (fees,
    interest) that belong to no client. The firm's direction code decides
    whether the amount is a debit (money in) or a credit (money out)."""
    entries = _extract("cash_book", accounts=raw_accounts, portfolios=raw_portfolios)
    for entry in entries:
        direction = entry.pop("direction")
        amount = entry.pop("amount")
        column = FIRM_DIRECTION_CODES.get(direction)
        if column is None:
            raise ValueError(
                f"{entry['source']}: direction must be "
                f"{' or '.join(FIRM_DIRECTION_CODES)}, got {direction!r}")
        entry["debit"] = amount if column == "debit" else None
        entry["credit"] = amount if column == "credit" else None
    return entries


# ---------------- Liquet's rule for repeated copies ----------------

def _one_per_id(records: list[dict], id_field: str, what: str) -> list[dict]:
    """Keep one record per id when the firm copies the same thing into several
    places (a client in each portfolio, a security in each trade).

    Copies must agree; if two differ, stop and name both places. Liquet never
    silently picks one (canonical check 7). The first copy's `source` is kept."""
    by_id = {}
    for record in records:
        details = {k: v for k, v in record.items() if k != "source"}
        record_id = record[id_field]
        if record_id in by_id:
            first = by_id[record_id]
            if {k: v for k, v in first.items() if k != "source"} != details:
                raise ValueError(
                    f"{what} {record_id}: details differ between {first['source']} "
                    f"and {record['source']}")
            continue   # same thing, already recorded
        by_id[record_id] = record
    return list(by_id.values())


if __name__ == "__main__":
    june = Path("tests/fixtures/2026-06/firm")
    canonical = to_canonical(load_json(june / "accounts.json"),
                             load_json(june / "portfolios.json"))
    for collection, records in canonical.items():
        print(f"{collection}: {len(records)}")
    # expect: accounts 1, account_balances 1, clients 5, portfolios 5,
    #         securities 4, trades 5, cash_book 17