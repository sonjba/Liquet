"""What is still open in a run: the items no rule could explain.

    python work_list.py runs/ACC-KRW-CASH-01_2026-06/run-001

An item is open when the rules left it unmatched, or matched it with an amount
difference that no finding explains. Items a rule's finding covers are not open:
they already have a proposal waiting for a person.

The list is worked out from the run folder, never chosen by the agent, and it is
the only list a proposal may be about.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from run_store import load_run


def open_items(run_folder: Path) -> list[dict]:
    """Every open item in the run: unmatched lines and entries first, then differences."""
    run = load_run(run_folder)
    covered = set()
    for finding in run["findings"]:
        covered.update(finding["bank_ids"], finding["firm_ids"])

    items = []
    for side in ("bank", "firm"):
        for entry in run["leftovers"][side]:
            items.append({"item_id": entry["id"], "kind": "UNMATCHED", "side": side,
                          "amount": entry["amount"], "entry_type": entry["entry_type"],
                          "description": entry["description"]})

    differences = {}
    for decision in run["decisions"]:
        if decision["verdict"] != "CONGRUIT":
            continue
        if decision["bank_id"] in covered or decision["firm_id"] in covered:
            continue
        # a group match (R3) keeps its difference in the evidence, once per entry
        group_difference = decision["evidence"].get("group_difference")
        if group_difference is not None:
            difference = group_difference
        else:
            amounts = [d["difference"] for d in decision["differences"] if d["field"] == "amount"]
            difference = amounts[0] if amounts else "0.00"
        if Decimal(difference) == 0:
            continue
        item = differences.setdefault(decision["bank_id"], {
            "item_id": decision["bank_id"], "kind": "DIFFERENCE", "side": "match",
            "difference": difference, "firm_ids": [], "rule": decision["rule"]})
        item["firm_ids"].append(decision["firm_id"])

    return items + list(differences.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="List what is still open in a run.")
    parser.add_argument("run_folder", type=Path)
    items = open_items(parser.parse_args().run_folder)
    print(f"Open items: {len(items)}")
    for item in items:
        if item["kind"] == "UNMATCHED":
            print(f"  {item['item_id']:<30} {item['side']} only  {item['amount']:>10}"
                  f"  {item['entry_type']}  {item['description']}")
        else:
            print(f"  {item['item_id']:<30} {item['rule']} matched {len(item['firm_ids'])} entries,"
                  f" difference {item['difference']} not explained")