"""facts.py: the facts code gathers about one open item, before Claude sees it."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from liquet.review.facts import facts_for
from liquet.pipeline.run_month import main as run_month

JUNE = Path(__file__).parent.parent / "fixtures" / "2026-06"
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    return run_month(SOURCES, tmp_path_factory.mktemp("runs"), RUN_AT)["folder"]


def test_a_bank_line_gets_the_firm_entries_with_its_amount(run):
    facts = facts_for(run, "ACC-KRW-CASH-01:2026-06:L12")
    assert facts["open_item"]["amount"] == "-45.00"
    assert facts["firm_entries_with_the_same_amount"] == []   # the fee was never booked


def test_a_check_skips_an_open_item_that_is_not_its_kind(run):
    facts = facts_for(run, "CE-2026-06-0008")                 # a firm entry, not a bank line
    assert "firm_entries_with_the_same_amount" not in facts


def test_an_item_a_rule_matched_gets_no_facts(run):
    with pytest.raises(ValueError, match="not open"):
        facts_for(run, "ACC-KRW-CASH-01:2026-06:L2")          # matched by R1


def test_a_firm_entry_sees_the_decoy_and_who_it_belongs_to(run):
    facts = facts_for(run, "CE-2026-06-0008")                 # Hart Family Trust's 5,000
    assert facts["bank_lines_with_the_same_amount"] == [
        "ACC-KRW-CASH-01:2026-06:L8 2026-06-18 5000.00 FASTER PAYMENT NAIR P"
        " (already matched to CE-2026-06-0007 by R4)"]


def test_a_difference_gets_its_bank_line_entries_and_total(run):
    facts = facts_for(run, "ACC-KRW-CASH-01:2026-06:L11")     # five June fees in one transfer
    assert facts["bank_line"].endswith("-1562.50 TRANSFER KRW FEE ACCOUNT")
    assert len(facts["firm_entries_in_the_match"]) == 5
    assert facts["firm_entries_total"] == "-1598.50"          # 36.00 more than the bank


def test_facts_say_which_records_were_examined(run):
    assert facts_for(run, "CE-2026-06-0008")["examined"] == ["ACC-KRW-CASH-01:2026-06:L8"]
    assert facts_for(run, "ACC-KRW-CASH-01:2026-06:L12")["examined"] == []
    assert len(facts_for(run, "ACC-KRW-CASH-01:2026-06:L11")["examined"]) == 5