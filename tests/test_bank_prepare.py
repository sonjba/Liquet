from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import bank_reader
from bank_prepare import bank_entry_type, bank_to_item

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
ITEM_KEYS = {"id", "side", "date", "expected_date", "amount",
             "reference", "entry_type", "description", "party", "domicile"}


@pytest.fixture(scope="module")
def june_items():
    _, lines = bank_reader.read_statement(JUNE / "statement_header.json",
                                          JUNE / "bank_statement.csv")
    return [bank_to_item(line) for line in lines]


# ---------------- bank_entry_type ----------------

@pytest.mark.parametrize("description, expected", [
    ("SUBSCRIPTION CL-001 HART A", "SUBSCRIPTION"),
    ("SETTLEMENT BUY 400 ALBN", "TRADE_SETTLEMENT"),
    ("DIVIDEND ATIT NET OF TAX", "DIVIDEND"),
    ("WITHDRAWAL CL-004 REID T", "WITHDRAWAL"),
    ("TRANSFER KRW FEE ACCOUNT", "MANAGEMENT_FEE"),
    ("CUSTODY FEE JUNE", "CUSTODY_FEE"),
    ("CREDIT INTEREST JUNE", "INTEREST"),
    ("FASTER PAYMENT NAIR P", None),
])
def test_june_descriptions_get_the_right_type(description, expected):
    assert bank_entry_type(description) == expected


def test_case_and_spaces_do_not_matter():
    assert bank_entry_type("  dividend atit ") == "DIVIDEND"


def test_only_the_start_of_the_description_counts():
    assert bank_entry_type("REVERSAL OF DIVIDEND") is None


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