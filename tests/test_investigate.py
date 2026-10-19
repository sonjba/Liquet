"""investigate.py, with answers Claude really gave before: no API key, no cost, same every time."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from liquet.review.investigate import ReplayClaude, investigate
from run_month import main as run_month
from score import score
from liquet.review.work_list import open_items

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}
ANSWERS = JUNE / "claude_answers.jsonl"      # copied from a real run's investigations.jsonl
KEY = json.loads((JUNE / "answer_key.json").read_text(encoding="utf-8"))
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def june_run(tmp_path_factory):
    return run_month(SOURCES, tmp_path_factory.mktemp("runs"), RUN_AT)["folder"]


@pytest.fixture
def run(june_run, tmp_path):
    folder = tmp_path / "run-001"
    shutil.copytree(june_run, folder)
    return folder


def test_replayed_june_answers_score_five_right_and_one_open(run):
    client = ReplayClaude(ANSWERS)
    outcomes = {item["item_id"]: investigate(client, run, item["item_id"], "replay:test")["outcome"]
                for item in open_items(run)}
    assert outcomes["CE-2026-06-0008"] == "NON_LIQUET, nothing proposed"
    assert sum(outcome.startswith("saved as") for outcome in outcomes.values()) == 3
    verdicts = [r["verdict"] for r in score(run, KEY)]
    assert (verdicts.count("RIGHT"), verdicts.count("WRONG"), verdicts.count("OPEN")) == (5, 0, 1)


def test_every_call_is_logged_with_where_its_answer_came_from(run):
    investigate(ReplayClaude(ANSWERS), run, "CE-2026-06-0008", "replay:test")
    logged = json.loads((run / "investigations.jsonl").read_text(encoding="utf-8"))
    assert (logged["source"], logged["by"]) == ("replay:test", "quaestor")
    assert logged["examined"] == ["ACC-KRW-CASH-01:2026-06:L8"]
    assert '"examined"' not in logged["question"]           # ids for the graph, not for Claude


def test_a_replay_with_no_answer_for_the_item_says_so(run, tmp_path):
    empty = tmp_path / "none.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no answer"):
        investigate(ReplayClaude(empty), run, "CE-2026-06-0008", "replay:test")