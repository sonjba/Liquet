"""Save one month's run to its own folder, and load it back.

This is the handover between the two phases: the rules (run_month.py) end by
saving here, and the agent and the person start by loading from here.

One folder per account and month, e.g. runs/ACC-KRW-CASH-01_2026-06/:
    run.json        when it ran, the statement, and which input files (with a
                    fingerprint of each, so you can tell later exactly what was read)
    decisions.json  every R1-R4 decision
    findings.json   every Finding, stamped with created_at
    leftovers.json  the bank and firm items no rule could settle

Money is saved as text ("-225.00") and dates as "2026-06-30", the same rule as
the canonical format: JSON numbers are floats, and floats can change money.
A folder that already exists is never overwritten: it may hold approvals.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


def run_folder_name(header: dict) -> str:
    """ACC-KRW-CASH-01_2026-06. No ':' as in the statement id: Windows forbids it in names."""
    return f"{header['account_id']}_{header['period_start']:%Y-%m}"


def save_run(month: dict, runs_dir: Path, run_at: datetime, inputs: dict[str, Path]) -> Path:
    """Write the month's result to runs_dir/<account>_<month>/ and return that folder.

    run_at is passed in, not read from the clock here, so a test can give a
    fixed time and get the same files every time.
    """
    header, result = month["header"], month["result"]
    folder = Path(runs_dir) / run_folder_name(header)
    if folder.exists():
        raise FileExistsError(f"{folder} already exists; a saved run is never overwritten")
    folder.mkdir(parents=True)

    run = {
        "statement_id": header["statement_id"],
        "account_id": header["account_id"],
        "period_start": header["period_start"],
        "period_end": header["period_end"],
        "run_at": run_at.isoformat(),
        "inputs": {name: {"path": str(path), "sha256": _sha256(Path(path))}
                   for name, path in inputs.items()},
        "counts": {"decisions": len(result["decisions"]),
                   "findings": len(result["findings"]),
                   "leftover_bank": len(result["unmatched_bank"]),
                   "leftover_firm": len(result["unmatched_firm"])},
    }
    findings = [dict(finding, created_at=run_at.isoformat()) for finding in result["findings"]]
    leftovers = {"bank": result["unmatched_bank"], "firm": result["unmatched_firm"]}

    _write(folder / "run.json", run)
    _write(folder / "decisions.json", result["decisions"])
    _write(folder / "findings.json", findings)
    _write(folder / "leftovers.json", leftovers)
    return folder


def load_run(folder: Path) -> dict:
    """Read a saved run back: {"run", "decisions", "findings", "leftovers"}.
    Money and dates come back as text, exactly as saved."""
    folder = Path(folder)
    return {name: json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("run", "decisions", "findings", "leftovers")}


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, default=_to_text) + "\n", encoding="utf-8")


def _to_text(value):
    """How json.dumps saves what it can't save by itself."""
    if isinstance(value, Decimal):
        return str(value)                     # exact: "-225.00", never -225.0
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"can't save {type(value).__name__} to JSON: {value!r}")


def _sha256(path: Path) -> str:
    """A fingerprint of the file: changes if a single byte of it changes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()