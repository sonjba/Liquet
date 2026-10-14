"""Pair bank items with firm items, using the rules in docs/matching-rules.md."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

DATE_TOLERANCE = timedelta(days=1)

# R2a: the withholding tax rate the fixture's overseas dividends are paid net of.
# Real rates depend on the country and any tax treaty; v1 uses one fixed rate.
WITHHOLDING_TAX_RATE = Decimal("0.15")


def match(bank_items: list[dict], firm_items: list[dict], period_end: date) -> dict:
    """Run the rules in order; return decisions, findings and what's left on each side.

    period_end is the statement's last day: R5 needs it to tell which
    settlements belong to next month.
    """
    open_bank = list(bank_items)
    open_firm = list(firm_items)
    decisions = []
    findings = []

    _rule_r1(open_bank, open_firm, decisions)
    _rule_r2(open_bank, open_firm, decisions, findings)
    _rule_r3(open_bank, open_firm, decisions)
    _rule_r4(open_bank, open_firm, decisions)
    _rule_r5(open_firm, period_end, findings)

    return {"decisions": decisions,
            "findings": findings,
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
        firm = _one_by_reference(bank, open_firm)
        if firm is None:
            continue
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


def _rule_r2(open_bank, open_firm, decisions, findings) -> None:
    """R2 - Same reference, amount differs: the same transaction, with a difference.

    Same reference, exactly one candidate, money moving the same way (both in
    or both out), date within DATE_TOLERANCE, amounts differ. Verdict CONGRUIT;
    the amount difference (bank minus firm) goes into `differences`.
    If R2a recognises the difference as withholding tax, it adds a Finding;
    any other difference is left for the agent to explain.
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
        _rule_r2a(bank, firm, findings)
        open_bank.remove(bank)
        open_firm.remove(firm)


def _rule_r2a(bank: dict, firm: dict, findings) -> None:
    """R2a - Withholding tax: an overseas dividend paid net of tax.

    The entry is a dividend, its security is overseas, and the bank paid
    exactly WITHHOLDING_TAX_RATE less than the firm recorded. Plain arithmetic,
    nothing to judge: a Finding OMISSUM / WITHHOLDING_TAX, adjusting the book
    (the firm hasn't recorded the tax). Status PROPOSED: a person approves it.
    """
    if firm["entry_type"] != "DIVIDEND" or firm["domicile"] != "overseas":
        return
    tax = firm["amount"] - bank["amount"]
    if tax != firm["amount"] * WITHHOLDING_TAX_RATE:
        return
    findings.append({
        "finding_id": f"R2a:{firm['id']}",
        "rule": "R2a",
        "category": "OMISSUM",
        "type": "WITHHOLDING_TAX",
        "firm_ids": [firm["id"]],
        "bank_ids": [bank["id"]],
        "adjusts": "book",
        "adjustment": -tax,
        "evidence": {"gross": firm["amount"], "net_paid": bank["amount"],
                     "tax": tax, "rate": WITHHOLDING_TAX_RATE},
        "status": "PROPOSED",
        "proposed_by": "R2a",
        "decided_by": None,
    })


def _rule_r3(open_bank, open_firm, decisions) -> None:
    """R3 - One bank line, several entries: the bank paid a group in one go.

    Two or more open firm items share the bank line's reference, all move
    money the same way as the bank line, and all are expected within
    DATE_TOLERANCE of it. Each entry gets its own CONGRUIT decision to the
    same bank line. The group's total is compared with the bank amount; the
    difference (bank minus group total) goes into each decision's evidence,
    not into `differences`, because it belongs to the group, not to one entry.
    """
    for bank in list(open_bank):
        if bank["reference"] is None:
            continue
        group = [firm for firm in open_firm if firm["reference"] == bank["reference"]]
        if len(group) < 2:                    # one candidate was R1's or R2's job
            continue
        same_direction = all((firm["amount"] > 0) == (bank["amount"] > 0) for firm in group)
        on_time = all(abs(bank["date"] - firm["expected_date"]) <= DATE_TOLERANCE for firm in group)
        if not same_direction or not on_time:
            continue
        group_total = sum(firm["amount"] for firm in group)
        evidence = {
            "reference": bank["reference"],
            "group_size": len(group),
            "group_total": group_total,
            "bank_amount": bank["amount"],
            "group_difference": bank["amount"] - group_total,
        }
        for firm in group:
            decisions.append({
                "bank_id": bank["id"],
                "firm_id": firm["id"],
                "verdict": "CONGRUIT",
                "rule": "R3",
                "differences": [],
                "evidence": dict(evidence, lag_days=(bank["date"] - firm["expected_date"]).days),
            })
            open_firm.remove(firm)
        open_bank.remove(bank)


def _same_type_or_unknown(bank: dict, firm: dict) -> bool:
    """Types only rule a candidate out when both sides know their type."""
    return bank["entry_type"] is None or bank["entry_type"] == firm["entry_type"]


def _names_party(description: str, party: str | None) -> bool:
    """Does the bank's text name this party? True if any word of 3+ letters
    from the party's name appears as a whole word in the description.
    Deliberately simple: when it fits two candidates, R4 says NON LIQUET."""
    if not party:
        return False
    words = set(re.findall(r"[A-Z]+", description.upper()))
    return any(len(word) >= 3 and word in words for word in party.upper().split())


def _r4_decision(bank: dict, firm: dict, candidates: list[dict], verdict: str, reason: str) -> dict:
    """One R4 decision; every R4 decision lists all the candidates it chose between."""
    return {
        "bank_id": bank["id"],
        "firm_id": firm["id"],
        "verdict": verdict,
        "rule": "R4",
        "differences": [],
        "evidence": {"candidates": [c["id"] for c in candidates],
                     "lag_days": (bank["date"] - firm["expected_date"]).days,
                     "reason": reason},
    }


def _rule_r4(open_bank, open_firm, decisions) -> None:
    """R4 - No reference match: find candidates by amount and date.

    Candidates are open firm items with exactly the same amount, expected
    within DATE_TOLERANCE, and of the same entry type when the bank line's
    type is known.
      - one candidate:  CONGRUIT.
      - several, and the bank's text names exactly one candidate's client:
        CONGRUIT with that one, DISCREPAT to each of the others (they stay open).
      - several, and the text doesn't settle it: NON LIQUET to each candidate;
        nothing is settled, a person decides.
    """
    for bank in list(open_bank):
        candidates = [firm for firm in open_firm
                      if firm["amount"] == bank["amount"]
                      and abs(bank["date"] - firm["expected_date"]) <= DATE_TOLERANCE
                      and _same_type_or_unknown(bank, firm)]
        if not candidates:
            continue

        if len(candidates) == 1:
            decisions.append(_r4_decision(bank, candidates[0], candidates, "CONGRUIT",
                                          "only open item with this amount and date"))
            open_firm.remove(candidates[0])
            open_bank.remove(bank)
            continue

        named = [firm for firm in candidates if _names_party(bank["description"], firm["party"])]
        if len(named) == 1:
            chosen = named[0]
            decisions.append(_r4_decision(bank, chosen, candidates, "CONGRUIT",
                                          f"bank text names {chosen['party']}"))
            for other in candidates:
                if other is not chosen:
                    decisions.append(_r4_decision(
                        bank, other, candidates, "DISCREPAT",
                        f"same amount and date, but bank text names {chosen['party']}, "
                        f"not {other['party']}"))
            open_firm.remove(chosen)
            open_bank.remove(bank)
        else:
            for firm in candidates:
                decisions.append(_r4_decision(
                    bank, firm, candidates, "NON LIQUET",
                    f"{len(candidates)} candidates with this amount and date; "
                    "bank text does not name exactly one"))


def _rule_r5(open_firm, period_end: date, findings) -> None:
    """R5 - Settlement after the period: the money moves next month.

    An open trade-settlement entry whose expected date (the trade's settlement
    date) is after the statement's last day can't be on this statement. That is
    fully decided by the dates, so the rule writes a Finding: IN_TRANSITU.
    The entry is then accounted for and leaves the open list.

    The Finding adjusts the bank side: the bank balance will include this
    amount once it settles. Status PROPOSED: a person still approves it.
    """
    for firm in list(open_firm):
        if firm["entry_type"] != "TRADE_SETTLEMENT" or firm["expected_date"] <= period_end:
            continue
        findings.append({
            "finding_id": f"R5:{firm['id']}",
            "rule": "R5",
            "category": "IN_TRANSITU",
            "type": "OUTSTANDING_PAYMENT" if firm["amount"] < 0 else "OUTSTANDING_RECEIPT",
            "firm_ids": [firm["id"]],
            "bank_ids": [],
            "adjusts": "bank",
            "adjustment": firm["amount"],
            "evidence": {"reference": firm["reference"],
                         "settlement_date": firm["expected_date"],
                         "period_end": period_end},
            "status": "PROPOSED",
            "proposed_by": "R5",
            "decided_by": None,
        })
        open_firm.remove(firm)