"""workflow/month.py: the month as steps, and `liquet status` telling where a run stands.

June is walked one step at a time, as a person would over several days, and the
status is checked after each step: what is done, what waits, what comes next."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from liquet.cli import main as liquet
from liquet.pipeline.run_month import main as run_month
from liquet.review.close_month import close_month
from liquet.review.decide import record
from liquet.review.investigate import ReplayClaude, investigate
from liquet.review.work_list import open_items
from liquet.workflow.month import STEPS, status

FIXTURES = Path(__file__).parent.parent / "fixtures"
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)
JULY_RUN_AT = datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc)
AT = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
EXPLANATIONS = ["R2a:CE-2026-06-0004", "R5:CE-2026-06-0011", "P1", "P2", "P3"]
HART = "CE-2026-06-0008"


def files(month):
    folder = FIXTURES / month
    return {"header": folder / "statement_header.json", "lines": folder / "bank_statement.csv",
            "accounts": folder / "firm" / "accounts.json",
            "portfolios": folder / "firm" / "portfolios.json"}


@pytest.fixture(scope="module")
def june(tmp_path_factory):
    """June step by step; the status is taken after each step."""
    runs = tmp_path_factory.mktemp("runs")
    seen = {}
    run = run_month(files("2026-06"), runs, RUN_AT)["folder"]
    seen["after run"] = status(run)
    claude = ReplayClaude(FIXTURES / "2026-06" / "claude_answers.jsonl")
    for item in open_items(run):
        investigate(claude, run, item["item_id"], "replay:test")
    seen["after investigate"] = status(run)
    record(run, "APPROVED", "P1", "sonja", AT, "CONFIRMED")
    seen["after one decision"] = status(run)
    for name in EXPLANATIONS[:2] + EXPLANATIONS[3:]:
        record(run, "APPROVED", name, "sonja", AT, "CONFIRMED")
    seen["after every decision"] = status(run)
    close_month(run, "sonja", AT, "June reconciled", {HART: "not in June's bank; check July"})
    seen["after close"] = status(run)
    seen["july"] = status(run_month(files("2026-07"), runs, JULY_RUN_AT)["folder"])
    return seen


def test_the_steps_are_in_the_order_of_a_month():
    assert [step.name for step in STEPS] == ["run", "investigate", "propose", "decide", "close"]
    assert {step.actor for step in STEPS} == {"rules", "LLM", "person"}


def test_after_the_rules_claude_is_next(june):
    state = june["after run"]
    assert state["done"] == {"run": True, "investigate": False, "propose": False,
                             "decide": False, "close": False}
    assert state["waiting"] == ["R2a:CE-2026-06-0004", "R5:CE-2026-06-0011"]
    assert state["next"] == "investigate"


def test_after_claude_everything_waits_for_a_person(june):
    state = june["after investigate"]
    assert state["done"]["investigate"] and not state["done"]["decide"]
    assert state["waiting"] == EXPLANATIONS
    assert state["unexplained"] == [HART]          # Claude said NON LIQUET
    assert state["next"] == "decide"


def test_claudes_proposals_do_not_count_as_a_persons(june):
    # Claude's P1-P3 are in proposals.jsonl too; no person has proposed anything
    assert june["after investigate"]["done"]["propose"] is False


def test_each_decision_takes_one_off_the_list(june):
    assert june["after one decision"]["waiting"] == [n for n in EXPLANATIONS if n != "P1"]
    assert june["after one decision"]["next"] == "decide"


def test_when_everything_is_decided_the_month_can_close(june):
    state = june["after every decision"]
    assert state["waiting"] == []
    assert state["next"] == "close"                # Hart is carried with a reason at close


def test_a_closed_month_has_no_next_step(june):
    state = june["after close"]
    assert state["done"]["close"] and state["next"] is None


def test_july_says_what_it_brought_forward(june):
    assert june["july"]["brought_forward_from"] == "ACC-KRW-CASH-01_2026-06/run-001"


def test_liquet_status_prints_the_steps_and_what_comes_next(tmp_path, capsys):
    run = run_month(files("2026-06"), tmp_path, RUN_AT)["folder"]
    capsys.readouterr()
    assert liquet(["status", str(run)]) == 0
    out = capsys.readouterr().out
    assert "1. run          rules   done" in out
    assert "waiting for a person: R2a:CE-2026-06-0004, R5:CE-2026-06-0011" in out
    assert out.strip().endswith("Next: liquet investigate RUN")
