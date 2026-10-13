"""Turn bank lines into Liquet's matching shape.

Every item has: id, side, date, expected_date, amount (signed Decimal),
reference (None if empty), entry_type (None if unknown), description,
party (None on the bank side: the bank's text is in description).
firm_prepare.py gives firm entries the same shape.
"""

from __future__ import annotations

from bank_mapping import BANK_DESCRIPTION_TYPES


def bank_entry_type(description: str) -> str | None:
    """The entry type for a bank description, or None if no rule fits."""
    text = description.strip().upper()
    for start, entry_type in BANK_DESCRIPTION_TYPES:
        if text.startswith(start):
            return entry_type
    return None


def bank_to_item(line: dict) -> dict:
    """One bank line as a matching item."""
    return {
        "id": line["line_id"],
        "side": "bank",
        "date": line["date"],
        "expected_date": line["date"],   # the bank's date is when money moved
        "amount": line["amount"],
        "reference": line["reference"].strip() or None,
        "entry_type": bank_entry_type(line["description"]),
        "description": line["description"],
        "party": None,                   # the bank's text is in description
    }