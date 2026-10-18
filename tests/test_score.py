"""score.py: the builder's check of a run against the answer key. Never shown to the agent."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from propose import record_proposal
from run_month import main as run_month
from score import score

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}
KEY = json.loads((JUNE / "answer_key.json").read_text(encoding="utf-8"))
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)
AT = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def june_run(tmp_path_factory):
    return run_month(SOURCES, tmp_path_factory.mktemp("runs"), RUN_AT)["folder"]


@pytest.fixture
def run(june_run, tmp_path):
    folder = tmp_path / "run-001"
    shutil.copytree(june_run, folder)
    return folder


def verdicts(run):
    return {r["break"]: r["verdict"] for r in score(run, KEY)}


def test_the_rules_alone_explain_two_breaks(run):
    assert verdicts(run) == {"B1": "OPEN", "B2": "RIGHT", "B3": "RIGHT",
                             "B4": "OPEN", "B5": "OPEN", "B6": "OPEN"}


def test_a_right_proposal_scores_right(run):
    record_proposal(run, ["ACC-KRW-CASH-01:2026-06:L12"], "OMISSUM", "BANK_FEE", "book",
                    "-45.00", "June custody fee.", "quaestor", "agent", AT)
    assert verdicts(run)["B4"] == "RIGHT"


def test_a_wrong_type_scores_wrong(run):
    record_proposal(run, ["ACC-KRW-CASH-01:2026-06:L13"], "OMISSUM", "BANK_FEE", "book",
                    "212.37", "Called it a fee, but it is interest.", "quaestor", "agent", AT)
    assert verdicts(run)["B5"] == "WRONG"

def test_a_rejected_rule_finding_no_longer_counts(run):
    from decide import record
    record(run, "REJECTED", "R2a:CE-2026-06-0004", "sonja", AT, "NEEDS_EVIDENCE", "check the rate")
    assert verdicts(run)["B3"] == "OPEN"