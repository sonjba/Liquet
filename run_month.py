"""Run Liquet for one month, stage by stage (docs/pipeline.md draws the stages).

    receive  -> fingerprint the files that arrived
    ingest   -> THE DOOR: read the bank's and the firm's files into Liquet's format, check them
    store    -> keep the received files and the Liquet-format data in a new run folder,
                then read the data back from there
    prepare  -> both sides in one matching shape
    match    -> rules R1-R5 (and R2a)
    check    -> nothing matched twice, nothing lost
    save     -> decisions, findings, leftovers, and run.json last

Only `ingest` knows the outside formats. Every stage after `store` uses the
data read back from the run folder, so what is stored is provably what
matching used. A new bank or firm changes `ingest` (its readers and
mappings) and nothing else.

    python run_month.py --header ... --lines ... --accounts ... --portfolios ...
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from bank_prepare import bank_items
from bank_reader import read_statement
from firm_checks import check_canonical
from firm_connector import FirmFileConnector
from firm_prepare import firm_items
from match import match
from match_checks import check_match_result
from run_store import (fingerprints, load_data, new_run_folder, save_data, save_received,
                       save_results)

STAGES = ["receive", "ingest", "store", "prepare", "match", "check", "save"]


# ---------------- the door: the only stage that knows outside formats ----------------

def ingest(sources: dict[str, Path]) -> dict:
    """Read the bank's and the firm's files and return them in Liquet's format,
    checked. Each side's reader runs its own checks and stops on a problem."""
    header, lines = read_statement(sources["header"], sources["lines"])
    firm = FirmFileConnector(sources["accounts"], sources["portfolios"])
    check_canonical(firm.canonical, header["period_start"])
    entries = firm.get_cash_entries(header["account_id"],
                                    header["period_start"], header["period_end"])
    return {"bank_statement": {"header": header, "lines": lines},
            "firm_canonical": firm.canonical,
            "firm_cash_entries": entries}


# ---------------- store: keep it, then work only from what was kept ----------------

def store(runs_dir: Path, sources: dict[str, Path], read_fingerprints: dict[str, str],
          data: dict) -> tuple[Path, dict, dict]:
    """Make the run folder, copy in the received files, save the Liquet data,
    and read the data back. Returns (folder, received, data as stored)."""
    folder = new_run_folder(runs_dir, data["bank_statement"]["header"])
    received = save_received(folder, sources, read_fingerprints)
    save_data(folder, data)
    stored = load_data(folder)
    if stored != data:
        raise ValueError(f"{folder}/data: reading the saved data back does not give "
                         f"the same data; stopping before matching")
    return folder, received, stored


# ---------------- the whole month ----------------

def main(sources: dict[str, Path], runs_dir: Path, run_at: datetime) -> dict:
    """Run every stage in order. All data lives in `month`."""
    month = {"run_at": run_at}

    # 1. receive
    read_fingerprints = fingerprints(sources)

    # 2. ingest (the door)
    ingested = ingest(sources)

    # 3. store, and from here on use only what was stored
    month["folder"], received, data = store(runs_dir, sources, read_fingerprints, ingested)
    month["header"] = data["bank_statement"]["header"]

    # 4. prepare both sides in the same shape for matching
    month["bank_items"] = bank_items(data["bank_statement"])
    month["firm_items"] = firm_items(data["firm_canonical"], data["firm_cash_entries"])

    # 5. match
    month["result"] = match(month["bank_items"], month["firm_items"],
                            period_end=month["header"]["period_end"])

    # 6. check: nothing matched twice, nothing lost (stops the run if not)
    check_match_result(month["bank_items"], month["firm_items"], month["result"])

    # 7. save the results: the handover to the agent and the person
    save_results(month["folder"], month["header"], month["result"], run_at, received, STAGES)
    return month


def show(month: dict) -> None:
    """Print both sides and the matching result."""
    header = month["header"]
    print(f"Statement {header['statement_id']}: {header['period_start']} to {header['period_end']}")

    for title, items in (("Bank items", month["bank_items"]), ("Firm items", month["firm_items"])):
        print(f"\n{title}: {len(items)}")
        for item in items:
            short_id = item["id"].split(":")[-1]          # "L3" or "CE-2026-06-0002"
            print(f"  {short_id:<16} {item['expected_date']}  {item['amount']:>10}  "
                  f"{item['reference'] or '-':<16} {item['entry_type'] or '-':<17} {item['description']}")

    result = month["result"]
    print(f"\nDecisions: {len(result['decisions'])}")
    for d in result["decisions"]:
        diff = "".join(f"  diff {x['difference']}" for x in d["differences"])
        if "group_difference" in d["evidence"]:
            diff += f"  group diff {d['evidence']['group_difference']}"
        print(f"  {d['bank_id'].split(':')[-1]:<4} <-> {d['firm_id']}  "
              f"{d['rule']}  {d['verdict']}  lag {d['evidence']['lag_days']}d{diff}")
    print(f"\nFindings: {len(result['findings'])}")
    for f in result["findings"]:
        print(f"  {f['finding_id']:<22} {f['category']} / {f['type']}  "
              f"adjust {f['adjusts']} {f['adjustment']}  {f['status']}")

    print(f"\nUnmatched bank: {[i['id'].split(':')[-1] for i in result['unmatched_bank']]}")
    print(f"Unmatched firm: {[i['id'] for i in result['unmatched_firm']]}")
    print(f"\nSaved to {month['folder']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile one month.")
    parser.add_argument("--header", type=Path, required=True, help="bank statement header (JSON)")
    parser.add_argument("--lines", type=Path, required=True, help="bank statement lines (CSV)")
    parser.add_argument("--accounts", type=Path, required=True, help="firm accounts (JSON)")
    parser.add_argument("--portfolios", type=Path, required=True, help="firm portfolios (JSON)")
    parser.add_argument("--runs", type=Path, default=Path("runs"),
                        help="folder that holds every run (default: runs)")
    args = parser.parse_args()

    sources = {"header": args.header, "lines": args.lines,
               "accounts": args.accounts, "portfolios": args.portfolios}
    show(main(sources, args.runs, run_at=datetime.now(timezone.utc)))
