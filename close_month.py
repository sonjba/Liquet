"""Close a month: a person marks one run final, and Liquet writes what it hands to next month.

    python close_month.py RUN --by sonja --reason "June reconciled" \
        --carry CE-2026-06-0008 "Hart subscription not in June's bank; check July"

Closing refuses while any finding or proposal still waits for a person. It then
writes RUN/closing.json with everything next month must check first:
  EXPECTED     approved as in transit: the bank should show it next month
  UNEXPLAINED  still open; a person carries it, with a reason
Approved book corrections (fees, interest, book errors) are not carried: the firm
books them in the month they belong to.

Only one run per month can be final. The closing.json is what makes it final.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from decide import load_reviews
from propose import load_proposals
from liquet.store.run_store import load_run,load_liquet_format
from work_list import open_items
from facts import load_run_data

CLOSING = "closing.json"


def what_to_carry(run_folder, unexplained_reasons):
    """What this month hands to the next. Stops if anything still waits for a person."""
    findings = load_run(run_folder)["findings"]
    proposals = load_proposals(run_folder)
    reviews = {review["finding_id"]: review["kind"] for review in load_reviews(run_folder)}
    explanations = ([(f["finding_id"], f["bank_ids"] + f["firm_ids"], f["category"],
                      f["explanation"]) for f in findings] +
                    [(p["proposal_id"], p["item_ids"], p["category"], p["explanation"])
                     for p in proposals])

    waiting = [name for name, *_ in explanations if name not in reviews]
    if waiting:
        raise ValueError(f"still waiting for a person to decide: {', '.join(waiting)}")
    rejected_rules = [f["finding_id"] for f in findings if reviews[f["finding_id"]] == "REJECTED"]
    if rejected_rules:
        raise ValueError(f"a rule's finding was rejected ({', '.join(rejected_rules)}); "
                         f"Liquet can't carry those yet")

    carried, explained = [], set()
    for name, ids, category, explanation in explanations:
        if reviews[name] != "APPROVED":
            continue
        explained.update(ids)
        if category == "IN_TRANSITU":
            carried.append({"item_ids": ids, "status": "EXPECTED",
                            "explained_by": name, "reason": explanation})

    unexplained = [item["item_id"] for item in open_items(run_folder)
                   if item["item_id"] not in explained]
    missing = [item_id for item_id in unexplained if item_id not in unexplained_reasons]
    if missing:
        raise ValueError(f"still open, carry each with a reason: {', '.join(missing)}")
    for item_id in unexplained:
        carried.append({"item_ids": [item_id], "status": "UNEXPLAINED",
                        "explained_by": None, "reason": unexplained_reasons[item_id]})
    return carried

def record_of(record_id, run_data):
    """One carried bank line or firm entry, with what next month needs to recognise it."""
    for line in run_data["bank_side_data"]:
        if line["line_id"] == record_id:
            return {"id": record_id, "side": "bank", "date": str(line["date"]),
                    "expected_date": str(line["date"]), "amount": str(line["amount"]),
                    "reference": line["reference"], "entry_type": line["entry_type"],
                    "description": line["description"], "party": None, "domicile": None}
    for entry in run_data["firm_side_data"]:
        if entry["id"] == record_id:
            return {"id": record_id, "side": "firm", "date": str(entry["date"]),
                    "expected_date": str(entry["expected_date"]), "amount": str(entry["amount"]),
                    "reference": entry["reference"], "entry_type": entry["entry_type"],
                    "description": entry["description"], "party": entry["party"],
                    "domicile": entry["domicile"]}
    raise ValueError(f"{record_id} is not in this run's data")


def close_month(run_folder, by, at, reason, unexplained_reasons):
    """Mark this run final and write closing.json. One final run per month, never overwritten."""
    run_folder = Path(run_folder)
    for other in sorted(run_folder.parent.glob(f"run-*/{CLOSING}")):
        raise ValueError(f"{other.parent.name} is already the final run for this month")
    if not reason.strip():
        raise ValueError("closing a month needs a reason")

    carried = what_to_carry(run_folder, unexplained_reasons)
    run_data = load_run_data(run_folder)
    for item in carried:
        item["records"] = [record_of(record_id, run_data) for record_id in item["item_ids"]]
    run = load_run(run_folder)["run"]
    header = load_liquet_format(run_folder)["bank_statement"]["header"]
    closing = {"run_id": run["run_id"], "statement_id": run["statement_id"],
               "period_end": str(header["period_end"]), "closed_by": by,
               "closed_at": at.isoformat(), "reason": reason, "carried": carried}
    with open(run_folder / CLOSING, "x", encoding="utf-8") as f:   # "x": never overwrite
        json.dump(closing, f, indent=2)
    return closing


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mark a run final and carry what is left.")
    parser.add_argument("run_folder", type=Path)
    parser.add_argument("--by", required=True, help="your name: only a person closes a month")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--carry", nargs=2, action="append", default=[],
                        metavar=("ITEM_ID", "REASON"), help="carry an unexplained item")
    args = parser.parse_args()
    try:
        closing = close_month(args.run_folder, args.by, datetime.now(timezone.utc),
                              args.reason, dict(args.carry))
        print(f"Closed {closing['run_id']}: final for {closing['statement_id']}")
        for item in closing["carried"]:
            print(f"  carried {item['status']:<11} {', '.join(item['item_ids'])}  {item['reason']}")
    except ValueError as error:
        print(f"Not closed: {error}")