"""decide.py: a person's decision on a finding, one line in reviews.jsonl."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from liquet.review.decide import load_reviews, record
from run_month import main as run_month

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}
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


def test_no_decisions_yet_means_an_empty_list(run):
    assert load_reviews(run) == []


def test_a_decision_is_one_line_with_who_when_and_why(run):
    record(run, "APPROVED", "R5:CE-2026-06-0011", "sonja", AT, "CONFIRMED")
    [line] = (run / "reviews.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(line) == {"kind": "APPROVED", "finding_id": "R5:CE-2026-06-0011",
                                "by": "sonja", "at": "2026-07-03T10:00:00+00:00",
                                "reason_code": "CONFIRMED", "reason": ""}


def test_lines_are_only_added(run):
    record(run, "APPROVED", "R5:CE-2026-06-0011", "sonja", AT, "CONFIRMED")
    first = (run / "reviews.jsonl").read_text(encoding="utf-8")
    record(run, "REJECTED", "R2a:CE-2026-06-0004", "sonja", AT, "NEEDS_EVIDENCE", "check rate")
    assert (run / "reviews.jsonl").read_text(encoding="utf-8").startswith(first)
    assert [r["finding_id"] for r in load_reviews(run)] == ["R5:CE-2026-06-0011",
                                                            "R2a:CE-2026-06-0004"]


@pytest.mark.parametrize("kind, finding, code, reason, message", [
    ("MAYBE", "R5:CE-2026-06-0011", "CONFIRMED", "", "APPROVED or REJECTED"),
    ("APPROVED", "R9:NOTHING", "CONFIRMED", "", "no finding"),
    ("APPROVED", "R5:CE-2026-06-0011", "LOOKS_FINE", "", "reason code must be one of"),
    ("REJECTED", "R5:CE-2026-06-0011", "WRONG_PERIOD", "", "needs a reason"),
])
def test_a_wrong_decision_is_refused_and_nothing_is_written(run, kind, finding, code, reason,
                                                            message):
    with pytest.raises(ValueError, match=message):
        record(run, kind, finding, "sonja", AT, code, reason)
    assert load_reviews(run) == []


def test_a_finding_is_decided_once(run):
    record(run, "APPROVED", "R5:CE-2026-06-0011", "sonja", AT, "CONFIRMED")
    with pytest.raises(ValueError, match="already decided"):
        record(run, "REJECTED", "R5:CE-2026-06-0011", "sonja", AT, "OTHER", "changed my mind")
