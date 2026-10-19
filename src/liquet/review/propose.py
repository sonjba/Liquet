"""Proposals: an explanation for an open item, from the agent or a person.

    python propose.py RUN ACC-KRW-CASH-01:2026-06:L12 --category OMISSUM --type BANK_FEE \
        --adjusts book --adjustment -45.00 --by sonja \
        --explanation "June custody fee charged by the custodian, not yet booked."

A proposal has a finding's shape, so a person decides it the same way, with
decide.py. Rules write findings during the run; proposals come afterwards, from
the agent or a person.

Each proposal is one line added to RUN/proposals.jsonl, checked first. Lines are
only ever added, never changed.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from liquet.review.decide import load_reviews
from liquet.review.work_list import open_items

PROPOSALS = "proposals.jsonl"
PROPOSERS = ("agent", "person")
# Liquet's categories and the types each allows (README dictionary, answer keys).
TYPES = {
    "IN_TRANSITU": ("DEPOSIT_IN_TRANSIT", "OUTSTANDING_PAYMENT", "OUTSTANDING_RECEIPT"),
    "OMISSUM": ("BANK_FEE", "INTEREST", "WITHHOLDING_TAX"),
    "ERRATUM": ("BOOK_ERROR",),
}


def load_proposals(run_folder: Path) -> list[dict]:
    """Every proposal made on this run so far, oldest first."""
    path = Path(run_folder) / PROPOSALS
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def item_difference(item: dict) -> Decimal:
    """Bank minus book for one open item: what is missing from the book's point of view."""
    if item["kind"] == "DIFFERENCE":
        return Decimal(item["difference"])
    amount = Decimal(item["amount"])
    return amount if item["side"] == "bank" else -amount


def record_proposal(run_folder: Path, item_ids: list[str], category: str, type_: str,
                    adjusts: str, adjustment: str, explanation: str, by: str,
                    proposer: str, at: datetime, evidence: dict | None = None,
                    model: str | None = None) -> dict:
    """Check one proposal, then add it to the end of proposals.jsonl."""
    items = {item["item_id"]: item for item in open_items(run_folder)}
    proposals = load_proposals(run_folder)
    reviews = {r["finding_id"]: r["kind"] for r in load_reviews(run_folder)}
    waiting = {i for p in proposals if p["proposal_id"] not in reviews for i in p["item_ids"]}
    explained = {i for p in proposals if reviews.get(p["proposal_id"]) == "APPROVED"
                 for i in p["item_ids"]}

    if proposer not in PROPOSERS:
        raise ValueError(f"a proposal comes from {' or '.join(PROPOSERS)}, not {proposer!r}")
    if not item_ids:
        raise ValueError("a proposal names at least one open item")
    for item_id in item_ids:
        if item_id not in items:
            raise ValueError(f"{item_id} is not open in this run")
        if item_id in waiting:
            raise ValueError(f"{item_id} already has a proposal waiting for a person")
        if item_id in explained:
            raise ValueError(f"{item_id} is already explained by an approved proposal")
    if category not in TYPES:
        raise ValueError(f"category must be one of {', '.join(TYPES)}")
    if type_ not in TYPES[category]:
        raise ValueError(f"{category} allows the types {', '.join(TYPES[category])}")
    if adjusts not in ("book", "bank"):
        raise ValueError("a proposal adjusts the book or the bank")
    try:
        amount = Decimal(adjustment)
    except InvalidOperation:
        raise ValueError(f"adjustment {adjustment!r} is not an amount") from None
    # code does the arithmetic: the adjustment must close the items' difference exactly
    difference = sum(item_difference(items[i]) for i in item_ids)
    expected = difference if adjusts == "book" else -difference
    if amount != expected:
        raise ValueError(f"adjusting the {adjusts} by {adjustment} leaves the items unexplained:"
                         f" it should be {expected:+.2f}")
    if not explanation.strip():
        raise ValueError("a proposal needs an explanation")

    proposal = {"proposal_id": f"P{len(proposals) + 1}", "item_ids": item_ids,
                "category": category, "type": type_, "adjusts": adjusts,
                "adjustment": f"{amount:.2f}", "explanation": explanation,
                "evidence": evidence or {}, "proposed_by": by, "proposer": proposer,
                "model": model, "at": at.isoformat()}
    with open(Path(run_folder) / PROPOSALS, "a", encoding="utf-8") as f:
        f.write(json.dumps(proposal) + "\n")
    return proposal


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Propose an explanation for open items.")
    parser.add_argument("run_folder", type=Path)
    parser.add_argument("item_ids", nargs="+", help="ids from work_list.py")
    parser.add_argument("--category", required=True, choices=list(TYPES))
    parser.add_argument("--type", required=True, dest="type_")
    parser.add_argument("--adjusts", required=True, choices=["book", "bank"])
    parser.add_argument("--adjustment", required=True, help="e.g. -45.00")
    parser.add_argument("--explanation", required=True)
    parser.add_argument("--by", required=True, help="your name")
    args = parser.parse_args()
    try:
        p = record_proposal(args.run_folder, args.item_ids, args.category, args.type_,
                            args.adjusts, args.adjustment, args.explanation, args.by,
                            "person", datetime.now(timezone.utc))
        print(f"Saved: {p['proposal_id']} {p['category']} / {p['type']}, "
              f"adjust {p['adjusts']} {p['adjustment']}")
    except ValueError as error:
        print(f"Not saved: {error}")