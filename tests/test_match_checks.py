from pathlib import Path

import pytest

from liquet.matching.bank_prepare import bank_to_item
from liquet.door.bank.bank_reader import read_statement
from liquet.door.firm.firm_connector import JsonFirmConnector
from liquet.matching.firm_prepare import domiciles_by_ticker, firm_to_item, parties_by_portfolio
from liquet.matching.match import match
from liquet.matching.match_checks import (MatchCheckError, check_every_item_accounted_for,
                          check_match_result, check_one_congruit_per_firm_item)

JUNE = Path(__file__).parent / "fixtures" / "2026-06"


@pytest.fixture(scope="module")
def june():
    """June's prepared items and the real matching result."""
    header, lines = read_statement(JUNE / "statement_header.json", JUNE / "bank_statement.csv")
    firm = JsonFirmConnector(JUNE / "firm" / "accounts.json", JUNE / "firm" / "portfolios.json")
    trades = {t["trade_id"]: t for t in firm.canonical["trades"]}
    parties = parties_by_portfolio(firm.canonical)
    domiciles = domiciles_by_ticker(firm.canonical)
    entries = firm.get_cash_entries(header["account_id"], header["period_start"], header["period_end"])
    bank_items = [bank_to_item(line) for line in lines]
    firm_items = [firm_to_item(e, trades, parties, domiciles) for e in entries]
    return bank_items, firm_items, match(bank_items, firm_items, period_end=header["period_end"])


def _result(**parts) -> dict:
    """A small hand-made result; give only the parts a test needs."""
    result = {"decisions": [], "findings": [], "unmatched_bank": [], "unmatched_firm": []}
    result.update(parts)
    return result


def _congruit(bank_id: str, firm_id: str) -> dict:
    return {"bank_id": bank_id, "firm_id": firm_id, "verdict": "CONGRUIT"}


# ---------------- June passes ----------------

def test_june_result_passes_every_check(june):
    bank_items, firm_items, result = june
    check_match_result(bank_items, firm_items, result)       # raises if not


# ---------------- check 1 ----------------

def test_firm_entry_matched_twice_is_caught():
    result = _result(decisions=[_congruit("B1", "F1"), _congruit("B2", "F1")])
    assert check_one_congruit_per_firm_item(result) == ["check 1, F1: matched (CONGRUIT) 2 times"]


def test_discrepat_and_non_liquet_do_not_count_as_matches():
    result = _result(decisions=[_congruit("B1", "F1"),
                                {"bank_id": "B2", "firm_id": "F1", "verdict": "DISCREPAT"},
                                {"bank_id": "B3", "firm_id": "F1", "verdict": "NON LIQUET"}])
    assert check_one_congruit_per_firm_item(result) == []


def test_one_bank_line_for_several_entries_is_fine():
    # R3: one bank line, many firm entries, each firm entry once.
    result = _result(decisions=[_congruit("B1", "F1"), _congruit("B1", "F2")])
    assert check_one_congruit_per_firm_item(result) == []


# ---------------- check 2 ----------------

def test_lost_item_is_caught():
    problems = check_every_item_accounted_for([{"id": "F1"}], _result(), "firm")
    assert problems == ["check 2, firm F1: lost (neither settled nor left over)"]


def test_item_settled_and_left_over_is_caught():
    result = _result(decisions=[_congruit("B1", "F1")], unmatched_firm=[{"id": "F1"}])
    problems = check_every_item_accounted_for([{"id": "F1"}], result, "firm")
    assert problems == ["check 2, firm F1: settled and also left over"]


def test_item_left_over_twice_is_caught():
    result = _result(unmatched_bank=[{"id": "B1"}, {"id": "B1"}])
    problems = check_every_item_accounted_for([{"id": "B1"}], result, "bank")
    assert problems == ["check 2, bank B1: left over 2 times"]


def test_item_from_nowhere_is_caught():
    result = _result(decisions=[_congruit("B9", "F1")])
    problems = check_every_item_accounted_for([], result, "bank")
    assert problems == ["check 2, bank B9: not among the bank items"]


def test_item_explained_by_a_finding_counts_as_settled():
    result = _result(findings=[{"firm_ids": ["F1"], "bank_ids": []}])
    assert check_every_item_accounted_for([{"id": "F1"}], result, "firm") == []


# ---------------- check_match_result ----------------

def test_problems_stop_the_run_and_are_all_listed():
    result = _result(decisions=[_congruit("B1", "F1"), _congruit("B2", "F1")])
    with pytest.raises(MatchCheckError) as error:
        check_match_result([{"id": "B1"}, {"id": "B2"}, {"id": "B3"}], [{"id": "F1"}], result)
    assert error.value.problems == [
        "check 1, F1: matched (CONGRUIT) 2 times",
        "check 2, bank B3: lost (neither settled nor left over)",
    ]