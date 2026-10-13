"""Pair bank items with firm items, using the rules in docs/matching-rules.md."""

from __future__ import annotations

from datetime import timedelta

DATE_TOLERANCE = timedelta(days=1)


def match(bank_items: list[dict], firm_items: list[dict]) -> dict:
    """Run the rules in order; return decisions and what's left on each side."""
    open_bank = list(bank_items)
    open_firm = list(firm_items)
    decisions = []

    _rule_r1(open_bank, open_firm, decisions)
    # later: R2, R3, R4, R5

    return {"decisions": decisions,
            "unmatched_bank": open_bank,
            "unmatched_firm": open_firm}


def _rule_r1(open_bank, open_firm, decisions) -> None:
    """R1 - Exact: same reference, same amount, date within DATE_TOLERANCE.
    Matched items are removed from open_bank and open_firm."""
    for bank in list(open_bank):              # a copy: we remove from open_bank inside
        if bank["reference"] is None:
            continue
        candidates = [firm for firm in open_firm
                      if firm["reference"] == bank["reference"]]
        if len(candidates) != 1:              # none, or several (a group: R3's job)
            continue
        firm = candidates[0]
        lag = bank["date"] - firm["expected_date"]
        if firm["amount"] != bank["amount"] or abs(lag) > DATE_TOLERANCE:
            continue
        decisions.append({
            "bank_id": bank["id"],
            "firm_id": firm["id"],
            "verdict": "CONGRUIT",
            "rule": "R1",
            "differences": [],
            "evidence": {"reference": bank["reference"], "lag_days": lag.days},
        })
        open_bank.remove(bank)
        open_firm.remove(firm)