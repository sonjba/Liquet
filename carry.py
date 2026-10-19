"""What last month carried into this one: found in last month's final run, kept in this run.

Last month's closing.json is Liquet's own format in a run folder, so it does not go
through the door. It is copied into this month's run as brought_forward.json, and
matching uses the copy: what is stored is what was used.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from liquet.store.run_store import run_folder_name

BROUGHT_FORWARD = "brought_forward.json"


def previous_closing(runs_dir, header):
    """Last month's closing, or None if Liquet never ran last month for this account.
    Stops if last month was run but none of its runs is final yet."""
    previous = {"account_id": header["account_id"],
                "period_start": header["period_start"] - timedelta(days=1)}
    month_folder = Path(runs_dir) / run_folder_name(previous)
    if not month_folder.exists():
        return None
    closings = sorted(month_folder.glob("run-*/closing.json"))
    if not closings:
        raise ValueError(f"{month_folder.name} has runs but none is final: close it first")
    return json.loads(closings[0].read_text(encoding="utf-8"))


def save_brought_forward(folder, closing):
    """Keep last month's closing in this run, then read it back."""
    path = Path(folder) / BROUGHT_FORWARD
    path.write_text(json.dumps(closing, indent=2), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def carried_items(closing):
    """The carried records as matching items, each saying where it came from and why."""
    if closing is None:
        return []
    items = []
    for carried in closing["carried"]:
        for record in carried["records"]:
            items.append({
                "id": record["id"], "side": record["side"],
                "date": date.fromisoformat(record["date"]),
                "expected_date": date.fromisoformat(record["expected_date"]),
                "amount": Decimal(record["amount"]), "reference": record["reference"],
                "entry_type": record["entry_type"], "description": record["description"],
                "party": record["party"], "domicile": record["domicile"],
                "brought_forward": {"from_run": closing["run_id"], "status": carried["status"],
                                    "reason": carried["reason"]}})
    return items