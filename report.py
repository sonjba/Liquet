"""Read a saved run back to a person: the same report run_month.py prints.

    python report.py runs/ACC-KRW-CASH-01_2026-06/run-004

It only reads the run folder. It never changes anything.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bank_prepare import bank_items
from firm_prepare import firm_items
from run_month import show
from liquet.store.run_store import load_liquet_format, load_run


def load_month(run_folder: Path) -> dict:
    """Rebuild the `month` that show() prints, from a saved run folder."""
    data = load_liquet_format(run_folder)
    saved = load_run(run_folder)
    return {
        "folder": Path(run_folder),
        "header": data["bank_statement"]["header"],
        "bank_items": bank_items(data["bank_statement"]),
        "firm_items": firm_items(data["firm_canonical"], data["firm_cash_entries"]),
        "result": {"decisions": saved["decisions"],
                   "findings": saved["findings"],
                   "unmatched_bank": saved["leftovers"]["bank"],
                   "unmatched_firm": saved["leftovers"]["firm"]},
    }


if __name__ == "__main__":
    show(load_month(Path(sys.argv[1])))
