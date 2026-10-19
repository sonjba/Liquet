"""The bank door gives every line its entry type and a clean reference,
so nothing after bank_reader needs to know how this bank words things."""

from pathlib import Path

import pytest

from liquet.door.bank.bank_reader import bank_entry_type, read_statement

JUNE = Path(__file__).parent / "fixtures" / "2026-06"


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


def test_read_statement_puts_type_and_reference_on_every_line():
    _, lines = read_statement(JUNE / "statement_header.json", JUNE / "bank_statement.csv")
    settlement = next(line for line in lines if line["line_number"] == 3)
    assert settlement["entry_type"] == "TRADE_SETTLEMENT"
    assert settlement["reference"] == "TR-26060101"
    assert lines[-1]["reference"] is None          # empty in the CSV -> None, not ""
    assert all("entry_type" in line for line in lines)
