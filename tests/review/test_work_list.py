"""work_list.py: what is still open after the rules, checked against the June answer key."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from liquet.pipeline.run_month import main as run_month
from liquet.review.work_list import open_items

JUNE = Path(__file__).parent.parent / "fixtures" / "2026-06"
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def items(tmp_path_factory):
    run = run_month(SOURCES, tmp_path_factory.mktemp("runs"), RUN_AT)["folder"]
    return {item["item_id"]: item for item in open_items(run)}


def test_june_leaves_the_four_breaks_no_rule_explained(items):
    # answer key: B4 (L12), B5 (L13), B1 (CE-0008), B6 (L11's +36.00)
    assert set(items) == {"ACC-KRW-CASH-01:2026-06:L12", "ACC-KRW-CASH-01:2026-06:L13",
                          "CE-2026-06-0008", "ACC-KRW-CASH-01:2026-06:L11"}


def test_unmatched_items_carry_their_amount_and_type(items):
    l12 = items["ACC-KRW-CASH-01:2026-06:L12"]
    assert (l12["kind"], l12["side"], l12["amount"], l12["entry_type"]) == (
        "UNMATCHED", "bank", "-45.00", "CUSTODY_FEE")
    assert items["CE-2026-06-0008"]["side"] == "firm"


def test_a_group_difference_is_one_item_with_all_its_entries(items):
    l11 = items["ACC-KRW-CASH-01:2026-06:L11"]
    assert (l11["kind"], l11["difference"], l11["rule"]) == ("DIFFERENCE", "36.00", "R3")
    assert len(l11["firm_ids"]) == 5


def test_a_difference_a_finding_explains_is_not_open(items):
    # L5's -225.00 is covered by R2a's finding, which waits for a person instead
    assert "ACC-KRW-CASH-01:2026-06:L5" not in items
    assert "CE-2026-06-0004" not in items

def test_unmatched_items_carry_their_date(items):
    assert items["ACC-KRW-CASH-01:2026-06:L12"]["date"] == "2026-06-30"
    assert items["CE-2026-06-0008"]["date"] == "2026-06-19"   # 11 days before month end