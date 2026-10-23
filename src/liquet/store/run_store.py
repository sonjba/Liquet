"""Liquet's store: one folder per run, holding what came in, what it became, and
what the rules decided.
                 received: dict, stages: list[str], release: dict) -> None:
One folder per account and month, and inside it one folder per run, so a
month can be run again (for example after the firm corrects its books)
without touching the earlier run:

    runs/ACC-KRW-CASH-01_2026-06/run-001/
        received/                 the files exactly as they arrived (copies)
            header.json, lines.csv, accounts.json, portfolios.json
        liquet_format/            the same data in Liquet's format: from here
            bank_statement.json   on, nothing reads anything else
            firm_canonical.json
            firm_cash_entries.json
        decisions.json            every R1-R4 decision
        findings.json             every Finding, stamped with proposed_at
        leftovers.json            the bank and firm items no rule could settle
        run.json                  written last: when it ran, the statement,
                                  the received files and their fingerprints,
                                  the stages that ran, the counts

A run folder without run.json did not finish: received/ and liquet_format/ show how
far it got.

Money is saved as text ("-225.00") and dates as "2026-06-30", the same rule as
the canonical format: JSON numbers are floats, and floats can change money.
Nothing in a run folder is ever changed or overwritten: later events (reviews,
graph snapshots) are added next to it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# The two folders of a run: what arrived, and the same data after the door.
RECEIVED = "received"
LIQUET_FORMAT = "liquet_format"

# Which fields of a Liquet bank statement are dates and money. Saved as text,
# turned back into date and Decimal by load_liquet_format().
HEADER_DATES = ("period_start", "period_end")
HEADER_MONEY = ("opening_balance", "closing_balance")
LINE_DATES = ("date",)
LINE_MONEY = ("paid_in", "paid_out", "balance", "amount")   # paid_in/paid_out may be None


class InputsChangedError(ValueError):
    """A received file is not the file that was read: its fingerprint differs."""


# ---------------- the run folder ----------------

def run_folder_name(header: dict) -> str:
    """ACC-KRW-CASH-01_2026-06. No ':' as in the statement id: Windows forbids it in names."""
    return f"{header['account_id']}_{header['period_start']:%Y-%m}"


def next_run_folder(month_folder: Path) -> Path:
    """The next free run folder: run-001 if there is none yet, else one more
    than the highest number already there."""
    numbers = [int(p.name[4:]) for p in Path(month_folder).glob("run-*")
               if p.is_dir() and p.name[4:].isdigit()]
    return Path(month_folder) / f"run-{max(numbers, default=0) + 1:03d}"


def new_run_folder(runs_dir: Path, header: dict) -> Path:
    """Create runs_dir/<account>_<month>/run-NNN/ and return it."""
    folder = next_run_folder(Path(runs_dir) / run_folder_name(header))
    folder.mkdir(parents=True)             # fails if it exists: never overwrite
    return folder


def run_id(folder: Path) -> str:
    """ACC-KRW-CASH-01_2026-06/run-001"""
    folder = Path(folder)
    return f"{folder.parent.name}/{folder.name}"


# ---------------- received: the files as they arrived ----------------

def fingerprints(sources: dict[str, Path]) -> dict[str, str]:
    """{name: sha256} for each source file. Taken before the files are read."""
    return {name: _sha256(Path(path)) for name, path in sources.items()}


def save_received(folder: Path, sources: dict[str, Path],
                  read_fingerprints: dict[str, str]) -> dict[str, dict]:
    """Copy each source file into folder/received/ as <name><suffix>, and check
    each copy is the file that was read (same fingerprint). Returns what
    run.json records about them."""
    received_dir = Path(folder) / RECEIVED
    received_dir.mkdir()
    received = {}
    for name, path in sources.items():
        path = Path(path)
        copy = received_dir / f"{name}{path.suffix}"
        shutil.copyfile(path, copy)
        if _sha256(copy) != read_fingerprints[name]:
            raise InputsChangedError(f"{name}: {path} changed while the run was reading it")
        received[name] = {"file": f"received/{copy.name}", "original_path": str(path),
                          "sha256": read_fingerprints[name]}
    return received


# ---------------- data: the same data in Liquet's format ----------------

def save_liquet_format(folder: Path, data: dict) -> None:
    """Write the Liquet-format data into folder/liquet_format/:
    data = {"bank_statement": {"header", "lines"}, "firm_canonical": {...},
            "firm_cash_entries": [...]}"""
    data_dir = Path(folder) / LIQUET_FORMAT
    data_dir.mkdir()
    for name in ("bank_statement", "firm_canonical", "firm_cash_entries"):
        _write(data_dir / f"{name}.json", data[name])


def load_liquet_format(folder: Path) -> dict:
    """Read folder/liquet_format/ back, with dates and money as date and Decimal again:
    the same dict save_liquet_format() was given."""
    data_dir = Path(folder) / LIQUET_FORMAT
    if not data_dir.is_dir():
        raise FileNotFoundError(f"{folder} has no liquet_format/ folder: it was saved before "
                                f"Liquet stored its data that way. Run the month again to make "
                                f"a new run.")
    data = {name: json.loads((data_dir / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("bank_statement", "firm_canonical", "firm_cash_entries")}
    statement = data["bank_statement"]
    _restore(statement["header"], HEADER_DATES, HEADER_MONEY)
    for line in statement["lines"]:
        _restore(line, LINE_DATES, LINE_MONEY)
    return data


def _restore(record: dict, dates: tuple, money: tuple) -> None:
    for field in dates:
        record[field] = date.fromisoformat(record[field])
    for field in money:
        if record[field] is not None:
            record[field] = Decimal(record[field])


# ---------------- results ----------------

def save_results(folder: Path, header: dict, result: dict, run_at: datetime,
                 received: dict, stages: list[str], release: dict) -> None:
    """Write decisions, findings and leftovers, then run.json last.

    run_at is passed in, not read from the clock here, so a test can give a
    fixed time and get the same files every time.
    """
    folder = Path(folder)
    run = {
        "run_id": run_id(folder),
        "statement_id": header["statement_id"],
        "account_id": header["account_id"],
        "period_start": header["period_start"],
        "period_end": header["period_end"],
        "run_at": run_at.isoformat(),
        "received": received,
        "stages": stages,
        "release": release,
        "counts": {"decisions": len(result["decisions"]),
                   "findings": len(result["findings"]),
                   "leftover_bank": len(result["unmatched_bank"]),
                   "leftover_firm": len(result["unmatched_firm"])},
    }
    findings = [dict(finding, proposed_at=run_at.isoformat()) for finding in result["findings"]]
    leftovers = {"bank": result["unmatched_bank"], "firm": result["unmatched_firm"]}

    _write(folder / "decisions.json", result["decisions"])
    _write(folder / "findings.json", findings)
    _write(folder / "leftovers.json", leftovers)
    _write(folder / "run.json", run)       # last: its presence means the run finished


def load_run(folder: Path) -> dict:
    """Read a finished run's results back: {"run", "decisions", "findings", "leftovers"}.
    Money and dates come back as text, exactly as saved."""
    folder = Path(folder)
    if not (folder / "run.json").exists():
        raise FileNotFoundError(f"{folder} has no run.json: the run did not finish")
    return {name: json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("run", "decisions", "findings", "leftovers")}


# ---------------- helpers ----------------

def _write(path: Path, data) -> None:
    if path.exists():
        raise FileExistsError(f"{path} already exists; a run's files are never overwritten")
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
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
