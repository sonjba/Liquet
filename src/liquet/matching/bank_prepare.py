"""Turn Liquet bank lines into Liquet's matching shape.

Every item has: id, side, date, expected_date, amount (signed Decimal),
reference (None if empty), entry_type (None if unknown), description,
party and domicile (None on the bank side: the bank's text is in description).
firm_prepare.py gives firm entries the same shape.

The lines come in Liquet's format (bank_reader.py already set reference and
entry_type), so nothing here knows anything about a particular bank.
"""

from __future__ import annotations


def bank_to_item(line: dict) -> dict:
    """One bank line as a matching item."""
    return {
        "id": line["line_id"],
        "side": "bank",
        "date": line["date"],
        "expected_date": line["date"],   # the bank's date is when money moved
        "amount": line["amount"],
        "reference": line["reference"],
        "entry_type": line["entry_type"],
        "description": line["description"],
        "party": None,                   # the bank's text is in description
        "domicile": None,
    }


def bank_items(statement: dict) -> list[dict]:
    """Every line of a stored bank statement ({"header", "lines"}) as an item."""
    return [bank_to_item(line) for line in statement["lines"]]
