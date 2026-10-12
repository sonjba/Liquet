"""Turn firm cash entries into Liquet's matching shape.

Same 8 keys as bank_prepare.py. The canonical data keeps money as text and
dates as text (canonical-format.md); this is where they become Decimal and date.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal


def signed_amount(entry: dict) -> Decimal:
    """Money in (debit) is +, money out (credit) is -, like the bank's amount."""
    if entry["debit"] is not None:
        return Decimal(entry["debit"])
    return -Decimal(entry["credit"])


def expected_date(entry: dict, trades: dict[str, dict]) -> date:
    """When the bank should show this entry.

    A trade settlement is booked by the firm on the trade date, but the money
    moves on the settlement date, so that's when the bank shows it.
    """
    if entry["entry_type"] == "TRADE_SETTLEMENT":
        trade = trades.get(entry["trade_id"])
        if trade is None:
            raise ValueError(f"{entry['entry_id']}: trade {entry['trade_id']!r} not found")
        return date.fromisoformat(trade["settlement_date"])
    return date.fromisoformat(entry["date"])


def firm_to_item(entry: dict, trades: dict[str, dict]) -> dict:
    """One firm cash entry as a matching item."""
    return {
        "id": entry["entry_id"],
        "side": "firm",
        "date": date.fromisoformat(entry["date"]),
        "expected_date": expected_date(entry, trades),
        "amount": signed_amount(entry),
        "reference": entry["reference"] or None,
        "entry_type": entry["entry_type"],
        "description": entry["description"],
    }