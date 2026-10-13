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
    _rule_r2(open_bank, open_firm, decisions)
    # later: R3, R4, R5

    return {"decisions": decisions,
            "unmatched_bank": open_bank,
            "unmatched_firm": open_firm}


def _one_by_reference(bank: dict, open_firm: list[dict]) -> dict | None:
    """The single open firm item with the bank item's reference, or None
    (no reference, no candidate, or several - a group is R3's job)."""
    if bank["reference"] is None:
        return None
    candidates = [firm for firm in open_firm if firm["reference"] == bank["reference"]]
    return candidates[0] if len(candidates) == 1 else None


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


def _rule_r2(open_bank, open_firm, decisions) -> None:
    """R2 - Same reference, amount differs: the same transaction, with a difference.

    Same reference, exactly one candidate, money moving the same way (both in
    or both out), date within DATE_TOLERANCE, amounts differ. Verdict CONGRUIT;
    the amount difference (bank minus firm) goes into `differences`.
    Explaining the difference (R2a, or the agent) is a separate step.
    """
    for bank in list(open_bank):
        firm = _one_by_reference(bank, open_firm)
        if firm is None:
            continue
        lag = bank["date"] - firm["expected_date"]
        same_direction = (bank["amount"] > 0) == (firm["amount"] > 0)
        if not same_direction or abs(lag) > DATE_TOLERANCE:
            continue
        decisions.append({
            "bank_id": bank["id"],
            "firm_id": firm["id"],
            "verdict": "CONGRUIT",
            "rule": "R2",
            "differences": [{"field": "amount",
                             "bank": bank["amount"],
                             "firm": firm["amount"],
                             "difference": bank["amount"] - firm["amount"]}],
            "evidence": {"reference": bank["reference"], "lag_days": lag.days},
        })
        open_bank.remove(bank)
        open_firm.remove(firm)