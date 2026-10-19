"""Carrying items from one month into the next: June closes, July checks what June left.

R0 clears a carried item when it arrives; what doesn't arrive stays open in July."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from liquet.review.close_month import close_month
from liquet.review.decide import record
from liquet.review.investigate import ReplayClaude, investigate
from run_month import main as run_month
from liquet.store.run_store import load_run
from liquet.review.work_list import open_items

FIXTURES = Path(__file__).parent / "fixtures"


def files(month):
    folder = FIXTURES / month
    return {"header": folder / "statement_header.json", "lines": folder / "bank_statement.csv",
            "accounts": folder / "firm" / "accounts.json",
            "portfolios": folder / "firm" / "portfolios.json"}


JUNE_RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)
JULY_RUN_AT = datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc)
AT = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
JULY = "ACC-KRW-CASH-01:2026-07:"


def run_and_review_june(runs):
    """June as a person leaves it: rules, Claude's replayed answers, everything decided."""
    june = run_month(files("2026-06"), runs, JUNE_RUN_AT)["folder"]
    claude = ReplayClaude(FIXTURES / "2026-06" / "claude_answers.jsonl")
    for item in open_items(june):
        investigate(claude, june, item["item_id"], "replay:test")
    for name in ["R2a:CE-2026-06-0004", "R5:CE-2026-06-0011", "P1", "P2", "P3"]:
        record(june, "APPROVED", name, "sonja", AT, "CONFIRMED")
    return june


@pytest.fixture(scope="module")
def two_months(tmp_path_factory):
    runs = tmp_path_factory.mktemp("runs")
    june = run_and_review_june(runs)
    close_month(june, "sonja", AT, "June reconciled",
                {"CE-2026-06-0008": "Hart subscription not in June's bank; check July"})
    july = run_month(files("2026-07"), runs, JULY_RUN_AT)["folder"]
    return {"june": june, "july": july}


def test_july_keeps_what_june_carried(two_months):
    kept = json.loads((two_months["july"] / "brought_forward.json").read_text(encoding="utf-8"))
    assert kept == json.loads((two_months["june"] / "closing.json").read_text(encoding="utf-8"))


def test_r0_clears_both_carried_items_when_they_arrive(two_months):
    r0 = {d["firm_id"]: d for d in load_run(two_months["july"])["decisions"] if d["rule"] == "R0"}
    hart, trade = r0["CE-2026-06-0008"], r0["CE-2026-06-0011"]
    assert (hart["bank_id"], hart["evidence"]["late"]) == (JULY + "L2", True)    # 12 days late
    assert (trade["bank_id"], trade["evidence"]["late"]) == (JULY + "L3", False)  # settled on time
    assert hart["evidence"]["carried_as"] == "UNEXPLAINED"


def test_july_leaves_only_its_own_breaks_open(two_months):
    assert {item["item_id"] for item in open_items(two_months["july"])} == {
        JULY + "L6", "CE-2026-07-0003",      # B1, the Reid pair
        JULY + "L9"}                         # B2, the custody fee


def test_july_cannot_start_while_june_is_not_final(tmp_path):
    run_and_review_june(tmp_path)            # June run and reviewed, but not closed
    with pytest.raises(ValueError, match="none is final: close it first"):
        run_month(files("2026-07"), tmp_path, JULY_RUN_AT)
    assert not (tmp_path / "ACC-KRW-CASH-01_2026-07").exists()   # nothing half-saved