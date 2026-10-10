"""Check the canonical data before Liquet uses it (canonical-format.md, checks 1-8).

These checks look only at the canonical shape, never at the firm's own data,
so any connector's output can be checked the same way.

Each check returns a list of problems; an empty list means it passed.
check_canonical() runs them all and stops the run if any problem is found,
listing every problem at once so they can all be fixed together. Each
problem names the check, the record and where the record came from (`source`).

Check 7 (repeated copies agree) can't be done here: by the time data is
canonical, the copies are already merged into one record. The connector
does it while merging (firm_connector._one_per_id).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

COLLECTIONS = ["accounts", "account_balances", "clients", "portfolios",
               "securities", "trades", "cash_book"]

# Each collection's id field (account_balances is identified by two fields).
ID_FIELDS = {
    "accounts": ("account_id",),
    "account_balances": ("account_id", "as_of"),
    "clients": ("client_id",),
    "portfolios": ("portfolio_id",),
    "securities": ("ticker",),
    "trades": ("trade_id",),
    "cash_book": ("entry_id",),
}

# (collection, field) -> the collection it points to. None is allowed only
# where canonical-format.md says "null": it is checked by check 4.
REFERENCES = [
    ("account_balances", "account_id", "accounts"),
    ("portfolios", "client_id", "clients"),
    ("portfolios", "account_id", "accounts"),
    ("trades", "portfolio_id", "portfolios"),
    ("trades", "account_id", "accounts"),
    ("trades", "ticker", "securities"),
    ("cash_book", "account_id", "accounts"),
    ("cash_book", "portfolio_id", "portfolios"),
    ("cash_book", "trade_id", "trades"),
    ("cash_book", "ticker", "securities"),
]
NULL_ALLOWED = {("cash_book", "portfolio_id"), ("cash_book", "trade_id"), ("cash_book", "ticker")}

# Entry types that belong to a client's portfolio, and those that belong to
# the account only (custody fee, interest).
CLIENT_ENTRY_TYPES = {"SUBSCRIPTION", "WITHDRAWAL", "TRADE_SETTLEMENT", "DIVIDEND", "MANAGEMENT_FEE"}
ACCOUNT_ENTRY_TYPES = {"CUSTODY_FEE", "INTEREST"}

# Money: text with exactly two decimals. Only a balance may be negative.
MONEY = re.compile(r"\d+\.\d{2}")
SIGNED_MONEY = re.compile(r"-?\d+\.\d{2}")
MONEY_FIELDS = [
    ("account_balances", "balance", SIGNED_MONEY),
    ("trades", "price", MONEY),
    ("trades", "costs", MONEY),
    ("trades", "settlement_amount", MONEY),
    ("cash_book", "debit", MONEY),     # None allowed: check 4 decides
    ("cash_book", "credit", MONEY),
]


class CanonicalCheckError(ValueError):
    """The canonical data failed one or more checks. `problems` lists them."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} problem(s) in the canonical data:\n  "
                         + "\n  ".join(problems))


def check_canonical(data: dict[str, list[dict]], period_start: date) -> None:
    """Run every check; raise CanonicalCheckError listing all problems found.

    period_start is the first day of the month being reconciled, e.g.
    date(2026, 6, 1) for June: check 8 needs the balance as of 31 May.
    """
    missing = [c for c in COLLECTIONS if c not in data]
    if missing:
        raise CanonicalCheckError([f"missing collection(s): {', '.join(missing)}"])

    # Money first: checks 3 and 5 do arithmetic on it, which only makes
    # sense once every amount is valid text.
    problems = check_money_is_text(data)
    if not problems:
        problems = (check_ids_are_unique(data)
                    + check_references_exist(data)
                    + check_trades_add_up(data)
                    + check_cash_entries(data)
                    + check_settlements_match_trades(data)
                    + check_opening_balance_exists(data, period_start))
    if problems:
        raise CanonicalCheckError(problems)


def _name(record: dict, collection: str) -> str:
    """How a problem names a record: its id, and where it came from."""
    record_id = "/".join(str(record.get(f)) for f in ID_FIELDS[collection])
    return f"{collection} {record_id} ({record.get('source', 'no source')})"


# ---------------- check 1 ----------------

def check_ids_are_unique(data: dict) -> list[str]:
    """Check 1: no two records in a collection share an id."""
    problems = []
    for collection, fields in ID_FIELDS.items():
        seen = {}
        for record in data[collection]:
            key = tuple(record.get(f) for f in fields)
            if key in seen:
                problems.append(f"check 1, {_name(record, collection)}: same id as "
                                f"{seen[key].get('source', 'no source')}")
            else:
                seen[key] = record
    return problems


# ---------------- check 2 ----------------

def check_references_exist(data: dict) -> list[str]:
    """Check 2: every id that points to another collection finds a record there."""
    ids = {c: {record.get(ID_FIELDS[c][0]) for record in data[c]}
           for c in ("accounts", "clients", "portfolios", "securities", "trades")}
    problems = []
    for collection, field, target in REFERENCES:
        for record in data[collection]:
            value = record.get(field)
            if value is None and (collection, field) in NULL_ALLOWED:
                continue
            if value not in ids[target]:
                problems.append(f"check 2, {_name(record, collection)}: {field} "
                                f"{value!r} is not in {target}")
    return problems


# ---------------- check 3 ----------------

def check_trades_add_up(data: dict) -> list[str]:
    """Check 3: BUY pays quantity x price + costs; SELL receives quantity x price - costs."""
    problems = []
    for trade in data["trades"]:
        quantity, side = trade.get("quantity"), trade.get("side")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            problems.append(f"check 3, {_name(trade, 'trades')}: quantity must be a "
                            f"whole number above 0, got {quantity!r}")
            continue
        if side not in ("BUY", "SELL"):
            problems.append(f"check 3, {_name(trade, 'trades')}: side must be BUY or "
                            f"SELL, got {side!r}")
            continue
        gross = quantity * Decimal(trade["price"])
        costs = Decimal(trade["costs"])
        expected = gross + costs if side == "BUY" else gross - costs
        if Decimal(trade["settlement_amount"]) != expected:
            problems.append(f"check 3, {_name(trade, 'trades')}: settlement_amount "
                            f"{trade['settlement_amount']}, expected {expected} "
                            f"({quantity} x {trade['price']} {'+' if side == 'BUY' else '-'} "
                            f"{trade['costs']})")
    return problems


# ---------------- check 4 ----------------

def check_cash_entries(data: dict) -> list[str]:
    """Check 4: exactly one of debit or credit, and the right links for the entry type."""
    problems = []
    for entry in data["cash_book"]:
        name, kind = _name(entry, "cash_book"), entry.get("entry_type")
        if (entry.get("debit") is None) == (entry.get("credit") is None):
            problems.append(f"check 4, {name}: needs exactly one of debit or credit")
        if kind in CLIENT_ENTRY_TYPES and entry.get("portfolio_id") is None:
            problems.append(f"check 4, {name}: a {kind} entry needs a portfolio_id")
        elif kind in ACCOUNT_ENTRY_TYPES and entry.get("portfolio_id") is not None:
            problems.append(f"check 4, {name}: a {kind} entry belongs to no portfolio")
        elif kind not in CLIENT_ENTRY_TYPES | ACCOUNT_ENTRY_TYPES:
            problems.append(f"check 4, {name}: unknown entry_type {kind!r}")
        if kind == "TRADE_SETTLEMENT" and entry.get("trade_id") is None:
            problems.append(f"check 4, {name}: a TRADE_SETTLEMENT needs a trade_id")
        if kind == "DIVIDEND" and entry.get("ticker") is None:
            problems.append(f"check 4, {name}: a DIVIDEND needs a ticker")
    return problems


# ---------------- check 5 ----------------

def check_settlements_match_trades(data: dict) -> list[str]:
    """Check 5: a trade settlement moves its trade's amount, in the right
    direction (BUY: money out, SELL: money in), for the same portfolio."""
    trades = {trade.get("trade_id"): trade for trade in data["trades"]}
    problems = []
    for entry in data["cash_book"]:
        trade = trades.get(entry.get("trade_id"))
        if entry.get("entry_type") != "TRADE_SETTLEMENT" or trade is None:
            continue   # a missing trade is reported by checks 2 and 4
        name = _name(entry, "cash_book")
        column = "credit" if trade["side"] == "BUY" else "debit"
        amount = entry.get(column)
        if amount is None:
            problems.append(f"check 5, {name}: a {trade['side']} should be a {column}")
        elif Decimal(amount) != Decimal(trade["settlement_amount"]):
            problems.append(f"check 5, {name}: amount {amount}, but trade "
                            f"{trade['trade_id']} settles {trade['settlement_amount']}")
        if entry.get("portfolio_id") != trade.get("portfolio_id"):
            problems.append(f"check 5, {name}: portfolio {entry.get('portfolio_id')}, but "
                            f"trade {trade['trade_id']} is for {trade.get('portfolio_id')}")
    return problems


# ---------------- check 6 ----------------

def check_money_is_text(data: dict) -> list[str]:
    """Check 6: money is text with exactly two decimals, never a JSON number.
    A JSON number is read as a float, which can quietly change an amount."""
    problems = []
    for collection, field, pattern in MONEY_FIELDS:
        for record in data[collection]:
            value = record.get(field)
            if value is None and collection == "cash_book":
                continue   # the empty side of debit/credit; check 4 decides
            if not isinstance(value, str) or not pattern.fullmatch(value):
                problems.append(f"check 6, {_name(record, collection)}: {field} must be "
                                f"text with two decimals, got {value!r}")
    return problems


# ---------------- check 8 ----------------

def check_opening_balance_exists(data: dict, period_start: date) -> list[str]:
    """Check 8: every account has a recorded balance for the day before the
    period starts (for June: 31 May). Without it, closing balances can't be compared."""
    day_before = (period_start - timedelta(days=1)).isoformat()
    have = {(b.get("account_id"), b.get("as_of")) for b in data["account_balances"]}
    return [f"check 8, {_name(account, 'accounts')}: no opening balance as of {day_before}"
            for account in data["accounts"]
            if (account.get("account_id"), day_before) not in have]