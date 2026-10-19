from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from liquet.door.bank import bank_reader
from liquet.matching.bank_prepare import bank_items, bank_to_item

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
ITEM_KEYS = {"id", "side", "date", "expected_date", "amount",
             "reference", "entry_type", "description", "party", "domicile"}


@pytest.fixture(scope="module")
def june_items():
    _, lines = bank_reader.read_statement(JUNE / "statement_header.json",
                                          JUNE / "bank_statement.csv")
    return [bank_to_item(line) for line in lines]


@pytest.fixture(scope="module")
def june_statement():
    header, lines = bank_reader.read_statement(JUNE / "statement_header.json",
                                               JUNE / "bank_statement.csv")
    return {"header": header, "lines": lines}


# ---------------- bank_to_item ----------------

def test_june_gives_twelve_items_with_the_same_keys(june_items):
    assert len(june_items) == 12
    assert all(set(item) == ITEM_KEYS for item in june_items)
    assert all(isinstance(item["amount"], Decimal) for item in june_items)
    assert all(isinstance(item["date"], date) for item in june_items)
    assert all(item["party"] is None and item["domicile"] is None for item in june_items)


def test_settlement_line_is_prepared_correctly(june_items):
    assert june_items[1] == {
        "id": "ACC-KRW-CASH-01:2026-06:L3",
        "side": "bank",
        "date": date(2026, 6, 3),
        "expected_date": date(2026, 6, 3),
        "amount": Decimal("-4852.40"),
        "reference": "TR-26060101",
        "entry_type": "TRADE_SETTLEMENT",
        "description": "SETTLEMENT BUY 400 ALBN",
        "party": None,
        "domicile": None,
    }


def test_line_without_reference_gets_none(june_items):
    assert june_items[-1]["reference"] is None


def test_type_and_reference_come_from_the_line_as_they_are():
    # bank_prepare decides nothing about a bank's wording: whatever the door
    # put on the line is what the item gets.
    line = {"line_id": "X:L2", "date": date(2026, 6, 1), "amount": Decimal("1.00"),
            "reference": None, "entry_type": "SOMETHING_NEW",
            "description": "DIVIDEND ATIT"}
    item = bank_to_item(line)
    assert (item["entry_type"], item["reference"]) == ("SOMETHING_NEW", None)


def test_bank_items_prepares_every_line_of_a_statement(june_statement, june_items):
    assert bank_items(june_statement) == june_items
