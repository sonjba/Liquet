import json
import sys
from decimal import Decimal
from pathlib import Path

from liquet.matching.firm_prepare import firm_items
from liquet.store.run_store import load_liquet_format, load_run
from work_list import open_items


def load_run_data(run_folder):
    """Everything the checks may look at, read once from the run folder."""
    liquet_format = load_liquet_format(run_folder)
    matched_to = {}
    for decision in load_run(run_folder)["decisions"]:
        if decision["verdict"] == "CONGRUIT":
            rule = decision["rule"]
            matched_to[decision["bank_id"]] = f"{decision['firm_id']} by {rule}"
            matched_to[decision["firm_id"]] = f"{decision['bank_id']} by {rule}"
    return {"bank_side_data": liquet_format["bank_statement"]["lines"],
            "firm_side_data": firm_items(liquet_format["firm_canonical"],
                                         liquet_format["firm_cash_entries"]),
            "matched_to": matched_to}


def note_if_matched(text, record_id, run_data):
    """Say who a line or entry already belongs to, so Claude is not misled by a decoy."""
    if record_id in run_data["matched_to"]:
        return f"{text} (already matched to {run_data['matched_to'][record_id]})"
    return text


def firm_entries_with_same_amount(open_item, run_data):
    """A bank line with no partner: does the firm's book have the same amount?"""
    if open_item["kind"] != "UNMATCHED" or open_item["side"] != "bank":
        return {}
    amount = Decimal(open_item["amount"])
    same = [entry for entry in run_data["firm_side_data"] if entry["amount"] == amount]
    return {"firm_entries_with_the_same_amount": [
                note_if_matched(f"{entry['id']} {entry['date']} {entry['amount']} {entry['description']}",
                                entry["id"], run_data)
                for entry in same],
            "examined": [entry["id"] for entry in same]}


def bank_lines_with_same_amount(open_item, run_data):
    """A firm entry with no partner: does the bank statement have the same amount?"""
    if open_item["kind"] != "UNMATCHED" or open_item["side"] != "firm":
        return {}
    amount = Decimal(open_item["amount"])
    same = [line for line in run_data["bank_side_data"] if line["amount"] == amount]
    return {"bank_lines_with_the_same_amount": [
                note_if_matched(f"{line['line_id']} {line['date']} {line['amount']} {line['description']}",
                                line["line_id"], run_data)
                for line in same],
            "examined": [line["line_id"] for line in same]}


def entries_in_the_match(open_item, run_data):
    """A match with a difference: the bank line, the firm entries the rule grouped, and their total."""
    if open_item["kind"] != "DIFFERENCE":
        return {}
    bank_line = next(line for line in run_data["bank_side_data"]
                     if line["line_id"] == open_item["item_id"])
    entries = [entry for entry in run_data["firm_side_data"]
               if entry["id"] in open_item["firm_ids"]]
    return {"bank_line": f"{bank_line['line_id']} {bank_line['date']} {bank_line['amount']} "
                         f"{bank_line['description']}",
            "firm_entries_in_the_match": [
                f"{entry['id']} {entry['date']} {entry['amount']} {entry['description']}"
                for entry in entries],
            "firm_entries_total": f"{sum(entry['amount'] for entry in entries):.2f}",
            "examined": [entry["id"] for entry in entries]}


CHECKS = [firm_entries_with_same_amount, bank_lines_with_same_amount, entries_in_the_match]


def facts_for(run_folder, item_id):
    """Everything Claude should know about one open item, gathered by code."""
    open_by_id = {open_item["item_id"]: open_item for open_item in open_items(run_folder)}
    if item_id not in open_by_id:
        raise ValueError(f"{item_id} is not open in this run")
    open_item = open_by_id[item_id]
    run_data = load_run_data(run_folder)
    facts = {"open_item": open_item}
    examined = []
    for check in CHECKS:
        found = check(open_item, run_data)
        examined += found.pop("examined", [])
        facts.update(found)
    facts["examined"] = examined
    return facts


if __name__ == "__main__":
    facts = facts_for(Path(sys.argv[1]), sys.argv[2])
    print(json.dumps(facts, indent=2))