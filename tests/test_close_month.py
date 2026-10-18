"""close_month.py: a month closes only when a person has decided everything,
and what it hands to next month is exactly what is still to come or still unexplained."""

import shutil
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest

from close_month import what_to_carry, close_month

from decide import record
from investigate import ReplayClaude, investigate
from run_month import main as run_month
from work_list import open_items

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)
AT = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
EXPLANATIONS = ["R2a:CE-2026-06-0004", "R5:CE-2026-06-0011", "P1", "P2", "P3"]
HART = "CE-2026-06-0008"


@pytest.fixture(scope="module")
def investigated(tmp_path_factory):
    """June after the rules and Claude's replayed answers: 2 findings and 3 proposals waiting."""
    run = run_month(SOURCES, tmp_path_factory.mktemp("runs"), RUN_AT)["folder"]
    claude = ReplayClaude(JUNE / "claude_answers.jsonl")
    for item in open_items(run):
        investigate(claude, run, item["item_id"], "replay:test")
    return run


@pytest.fixture
def run(investigated, tmp_path):
    folder = tmp_path / "run-001"
    shutil.copytree(investigated, folder)
    return folder


def decide_all(run):
    for name in EXPLANATIONS:
        record(run, "APPROVED", name, "sonja", AT, "CONFIRMED")


def test_a_month_cannot_close_while_anything_waits_for_a_person(run):
    with pytest.raises(ValueError, match="still waiting for a person to decide: R2a"):
        what_to_carry(run, {HART: "not in June's bank"})


def test_an_unexplained_item_needs_a_reason_to_be_carried(run):
    decide_all(run)
    with pytest.raises(ValueError, match=f"carry each with a reason: {HART}"):
        what_to_carry(run, {})


def test_june_carries_the_trade_in_transit_and_the_unexplained_hart_money(run):
    decide_all(run)
    carried = what_to_carry(run, {HART: "not in June's bank; check July"})
    assert [(c["item_ids"], c["status"], c["explained_by"]) for c in carried] == [
        (["CE-2026-06-0011"], "EXPECTED", "R5:CE-2026-06-0011"),
        ([HART], "UNEXPLAINED", None)]
    # the approved book corrections (P1-P3, R2a) stay in June: the firm books them there


def test_a_rejected_rule_finding_stops_the_close(run):
    record(run, "REJECTED", "R2a:CE-2026-06-0004", "sonja", AT, "NEEDS_EVIDENCE", "check the rate")
    for name in EXPLANATIONS[1:]:
        record(run, "APPROVED", name, "sonja", AT, "CONFIRMED")
    with pytest.raises(ValueError, match="rule's finding was rejected"):
        what_to_carry(run, {HART: "not in June's bank"})


def test_closing_writes_what_july_needs_to_recognise_each_item(run):
    decide_all(run)
    closing = close_month(run, "sonja", AT, "June reconciled", {HART: "not in June's bank"})
    assert json.loads((run / "closing.json").read_text(encoding="utf-8")) == closing
    assert (closing["closed_by"], closing["period_end"]) == ("sonja", "2026-06-30")
    hart = closing["carried"][1]["records"][0]
    assert (hart["side"], hart["date"], hart["amount"], hart["reference"], hart["party"]) == (
        "firm", "2026-06-19", "5000.00", "CL-005-SUB-0619", "Hart Family Trust")


def test_only_one_run_per_month_can_be_final(run):
    decide_all(run)
    close_month(run, "sonja", AT, "June reconciled", {HART: "not in June's bank"})
    second = run.parent / "run-002"
    shutil.copytree(run, second, ignore=shutil.ignore_patterns("closing.json"))
    with pytest.raises(ValueError, match="run-001 is already the final run"):
        close_month(second, "sonja", AT, "June again", {HART: "not in June's bank"})