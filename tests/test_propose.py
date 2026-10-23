"""propose.py: an explanation for an open item, checked, one line in proposals.jsonl."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from liquet.review.decide import record
from liquet.review.propose import load_proposals, record_proposal
from liquet.pipeline.run_month import main as run_month

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)
AT = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
L11 = "ACC-KRW-CASH-01:2026-06:L11"
L12 = "ACC-KRW-CASH-01:2026-06:L12"


@pytest.fixture(scope="module")
def june_run(tmp_path_factory):
    return run_month(SOURCES, tmp_path_factory.mktemp("runs"), RUN_AT)["folder"]


@pytest.fixture
def run(june_run, tmp_path):
    folder = tmp_path / "run-001"
    shutil.copytree(june_run, folder)
    return folder


def custody_fee(run, adjustment="-45.00", **changes):
    """The answer key's B4, as a person would propose it."""
    args = dict(item_ids=[L12], category="OMISSUM", type_="BANK_FEE", adjusts="book",
                adjustment=adjustment, explanation="June custody fee, not yet booked.",
                by="sonja", proposer="person", at=AT)
    args.update(changes)
    return record_proposal(run, **args)


def test_a_proposal_is_saved_as_one_line(run):
    proposal = custody_fee(run)
    assert proposal["proposal_id"] == "P1"
    lines = (run / "proposals.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [proposal] == load_proposals(run)


def test_the_answer_key_proposals_all_pass_the_checks(run):
    # B1, B5 and B6: each adjustment closes its item exactly
    record_proposal(run, ["CE-2026-06-0008"], "IN_TRANSITU", "DEPOSIT_IN_TRANSIT", "bank",
                    "5000.00", "Subscription reaches the bank in July.", "sonja", "person", AT)
    record_proposal(run, ["ACC-KRW-CASH-01:2026-06:L13"], "OMISSUM", "INTEREST", "book",
                    "212.37", "June credit interest, not yet booked.", "sonja", "person", AT)
    record_proposal(run, [L11], "ERRATUM", "BOOK_ERROR", "book", "36.00",
                    "Amelia Hart's fee booked as 473.50, should be 437.50.", "sonja", "person", AT)
    assert [p["proposal_id"] for p in load_proposals(run)] == ["P1", "P2", "P3"]


@pytest.mark.parametrize("changes, message", [
    ({"item_ids": ["ACC-KRW-CASH-01:2026-06:L2"]}, "not open"),   # matched by R1
    ({"item_ids": ["CE-2026-06-0004"]}, "not open"),              # covered by R2a's finding
    ({"item_ids": []}, "at least one"),
    ({"proposer": "rule"}, "agent or person"),
    ({"category": "GUESS"}, "category must be"),
    ({"type_": "INTEREST", "category": "ERRATUM"}, "allows the types"),
    ({"adjusts": "ledger"}, "book or the bank"),
    ({"adjustment": "lots"}, "not an amount"),
    ({"adjustment": "-40.00"}, "should be -45.00"),
    ({"adjusts": "bank"}, "should be \\+45.00"),
    ({"explanation": "  "}, "needs an explanation"),
])
def test_a_proposal_that_breaks_a_rule_is_not_saved(run, changes, message):
    with pytest.raises(ValueError, match=message):
        custody_fee(run, **changes)
    assert load_proposals(run) == []


def test_one_proposal_at_a_time_per_item(run):
    custody_fee(run)
    with pytest.raises(ValueError, match="already has a proposal waiting"):
        custody_fee(run)


def test_after_a_rejection_the_item_can_be_proposed_again(run):
    custody_fee(run)
    record(run, "REJECTED", "P1", "sonja", AT, "WRONG_AMOUNT", "check the fee schedule")
    assert custody_fee(run)["proposal_id"] == "P2"


def test_a_person_decides_a_proposal_like_a_finding(run):
    custody_fee(run)
    review = record(run, "APPROVED", "P1", "sonja", AT, "CONFIRMED")
    assert review["finding_id"] == "P1"


def test_an_approved_explanation_closes_the_item(run):
    custody_fee(run)
    record(run, "APPROVED", "P1", "sonja", AT, "CONFIRMED")
    with pytest.raises(ValueError, match="already explained"):
        custody_fee(run)