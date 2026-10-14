from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from bank_prepare import bank_to_item
from bank_reader import read_statement
from firm_connector import FirmFileConnector
from firm_prepare import domiciles_by_ticker, firm_to_item, parties_by_portfolio
from match import match

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
JUNE_END = date(2026, 6, 30)


# ---------------- helpers ----------------

def _item(side: str, item_id: str, **changes) -> dict:
    """A matching item; change only what a test needs."""
    item = {"id": item_id, "side": side,
            "date": date(2026, 6, 10), "expected_date": date(2026, 6, 10),
            "amount": Decimal("100.00"), "reference": "REF-1",
            "entry_type": "SUBSCRIPTION", "description": "test", "party": None,
            "domicile": None}
    item.update(changes)
    return item


def _bank(**changes) -> dict:
    return _item("bank", "B1", **changes)


def _firm(item_id: str = "F1", **changes) -> dict:
    return _item("firm", item_id, **changes)


@pytest.fixture(scope="module")
def june_result():
    header, lines = read_statement(JUNE / "statement_header.json", JUNE / "bank_statement.csv")
    firm = FirmFileConnector(JUNE / "firm" / "accounts.json", JUNE / "firm" / "portfolios.json")
    trades = {t["trade_id"]: t for t in firm.canonical["trades"]}
    parties = parties_by_portfolio(firm.canonical)
    domiciles = domiciles_by_ticker(firm.canonical)
    entries = firm.get_cash_entries(header["account_id"], header["period_start"], header["period_end"])
    return match([bank_to_item(line) for line in lines],
                 [firm_to_item(entry, trades, parties, domiciles) for entry in entries],
                 period_end=header["period_end"])


def _match(bank_items: list[dict], firm_items: list[dict]) -> dict:
    """match() for made-up items dated in June."""
    return match(bank_items, firm_items, period_end=JUNE_END)


def _short(bank_id: str) -> str:
    return bank_id.split(":")[-1]          # "ACC-KRW-CASH-01:2026-06:L3" -> "L3"


# ---------------- R1 on June ----------------

R1_JUNE_PAIRS = {
    "L2": "CE-2026-06-0001", "L3": "CE-2026-06-0002", "L4": "CE-2026-06-0003",
    "L6": "CE-2026-06-0005", "L7": "CE-2026-06-0006", "L9": "CE-2026-06-0009",
    "L10": "CE-2026-06-0010",
}


def _pairs_by_rule(result: dict, rule: str) -> dict[str, str]:
    return {_short(d["bank_id"]): d["firm_id"] for d in result["decisions"] if d["rule"] == rule}


def test_r1_pairs_exactly_the_expected_june_lines(june_result):
    assert _pairs_by_rule(june_result, "R1") == R1_JUNE_PAIRS


def test_every_r1_decision_is_congruit_with_no_differences(june_result):
    for decision in june_result["decisions"]:
        if decision["rule"] == "R1":
            assert decision["verdict"] == "CONGRUIT"
            assert decision["differences"] == []


def test_lines_the_rules_cannot_settle_are_left_over(june_result):
    left = {_short(item["id"]) for item in june_result["unmatched_bank"]}
    assert left == {"L12", "L13"}


def test_firm_entries_the_rules_cannot_settle_are_left_over(june_result):
    left = {item["id"] for item in june_result["unmatched_firm"]}
    assert left == {"CE-2026-06-0008"}


def test_settlement_is_compared_with_its_settlement_date(june_result):
    # L3 is 3 June at the bank; the firm booked it 1 June but expects 3 June.
    decision = next(d for d in june_result["decisions"] if _short(d["bank_id"]) == "L3")
    assert decision["evidence"]["lag_days"] == 0


def test_one_day_lag_is_recorded_in_the_evidence(june_result):
    # L6: bank 12 June, firm 11 June.
    decision = next(d for d in june_result["decisions"] if _short(d["bank_id"]) == "L6")
    assert decision["evidence"]["lag_days"] == 1


# ---------------- R1 boundaries ----------------

@pytest.mark.parametrize("bank_day, matches", [
    (date(2026, 6, 9), True),     # one day early
    (date(2026, 6, 11), True),    # one day late
    (date(2026, 6, 8), False),    # two days early
    (date(2026, 6, 12), False),   # two days late
])
def test_date_tolerance_is_one_day_either_way(bank_day, matches):
    result = _match([_bank(date=bank_day)], [_firm()])
    assert bool(result["decisions"]) == matches


def test_different_amount_is_not_r1():
    result = _match([_bank(amount=Decimal("90.00"))], [_firm()])
    assert [d["rule"] for d in result["decisions"]] == ["R2"]     # R2's, not R1's


def test_opposite_sign_is_not_a_match():
    # Money in at the bank must never pair with money out at the firm,
    # not by R1 and not by R2.
    result = _match([_bank(amount=Decimal("100.00"))], [_firm(amount=Decimal("-100.00"))])
    assert result["decisions"] == []


def test_missing_reference_is_not_r1():
    # Without a reference R1-R3 can't pair them; R4 (amount and date) can.
    result = _match([_bank(reference=None)], [_firm(reference=None)])
    assert [d["rule"] for d in result["decisions"]] == ["R4"]


def test_two_firm_items_with_the_same_reference_are_not_r1():
    # A group (one bank line, several entries) is R3's job, not R1's.
    result = _match([_bank()], [_firm("F1"), _firm("F2")])
    assert {d["rule"] for d in result["decisions"]} == {"R3"}


def test_a_firm_item_is_used_only_once():
    # Two identical bank lines, one firm entry: only one pair.
    first, second = _bank(), _item("bank", "B2")
    result = _match([first, second], [_firm()])
    assert len(result["decisions"]) == 1
    assert [item["id"] for item in result["unmatched_bank"]] == ["B2"]


def test_match_does_not_change_the_lists_it_was_given():
    bank_items, firm_items = [_bank()], [_firm()]
    _match(bank_items, firm_items)
    assert len(bank_items) == 1 and len(firm_items) == 1


# ---------------- R2: same reference, amount differs ----------------

def test_r2_pairs_the_june_dividend(june_result):
    assert _pairs_by_rule(june_result, "R2") == {"L5": "CE-2026-06-0004"}


def test_r2_records_the_difference_as_bank_minus_firm(june_result):
    decision = next(d for d in june_result["decisions"] if d["rule"] == "R2")
    assert decision["verdict"] == "CONGRUIT"
    assert decision["differences"] == [{
        "field": "amount",
        "bank": Decimal("1275.00"),
        "firm": Decimal("1500.00"),
        "difference": Decimal("-225.00"),
    }]


def test_r2_bank_paying_more_gives_a_positive_difference():
    result = _match([_bank(amount=Decimal("110.00"))], [_firm()])
    assert result["decisions"][0]["differences"][0]["difference"] == Decimal("10.00")


def test_r2_works_for_money_out_too():
    # Firm expected to pay 100, bank shows 105 paid: difference -5.00.
    result = _match([_bank(amount=Decimal("-105.00"))], [_firm(amount=Decimal("-100.00"))])
    assert result["decisions"][0]["rule"] == "R2"
    assert result["decisions"][0]["differences"][0]["difference"] == Decimal("-5.00")


def test_r2_needs_the_date_within_tolerance():
    result = _match([_bank(amount=Decimal("90.00"), date=date(2026, 6, 20))], [_firm()])
    assert result["decisions"] == []


def test_r2_leaves_groups_for_r3():
    result = _match([_bank(amount=Decimal("90.00"))], [_firm("F1"), _firm("F2")])
    assert {d["rule"] for d in result["decisions"]} == {"R3"}


def test_exact_match_is_taken_by_r1_not_r2():
    result = _match([_bank()], [_firm()])
    assert [d["rule"] for d in result["decisions"]] == ["R1"]


# ---------------- R3: one bank line, several entries ----------------

JUNE_FEES = ["CE-2026-06-0012", "CE-2026-06-0013", "CE-2026-06-0014",
             "CE-2026-06-0015", "CE-2026-06-0016"]


def test_r3_pairs_the_fee_transfer_with_all_five_fees(june_result):
    r3 = [d for d in june_result["decisions"] if d["rule"] == "R3"]
    assert {_short(d["bank_id"]) for d in r3} == {"L11"}
    assert sorted(d["firm_id"] for d in r3) == JUNE_FEES


def test_r3_records_the_group_total_and_difference(june_result):
    # Fees add up to -1598.50; the bank moved -1562.50: bank minus firm = +36.00.
    for decision in (d for d in june_result["decisions"] if d["rule"] == "R3"):
        assert decision["verdict"] == "CONGRUIT"
        assert decision["differences"] == []
        assert decision["evidence"]["group_size"] == 5
        assert decision["evidence"]["group_total"] == Decimal("-1598.50")
        assert decision["evidence"]["bank_amount"] == Decimal("-1562.50")
        assert decision["evidence"]["group_difference"] == Decimal("36.00")


def test_r3_group_that_adds_up_has_zero_difference():
    result = _match([_bank(amount=Decimal("100.00"))],
                   [_firm("F1", amount=Decimal("60.00")), _firm("F2", amount=Decimal("40.00"))])
    assert [d["evidence"]["group_difference"] for d in result["decisions"]] == [Decimal("0.00")] * 2
    assert result["unmatched_bank"] == [] and result["unmatched_firm"] == []


def test_r3_needs_every_entry_to_move_money_the_same_way():
    result = _match([_bank(amount=Decimal("100.00"))],
                   [_firm("F1", amount=Decimal("150.00")), _firm("F2", amount=Decimal("-50.00"))])
    assert result["decisions"] == []


def test_r3_needs_every_entry_within_the_date_tolerance():
    result = _match([_bank(amount=Decimal("100.00"))],
                   [_firm("F1", amount=Decimal("60.00")),
                    _firm("F2", amount=Decimal("40.00"), expected_date=date(2026, 6, 20))])
    assert result["decisions"] == []


def test_r3_ignores_bank_lines_without_a_reference():
    result = _match([_bank(reference=None)], [_firm("F1", reference=None), _firm("F2", reference=None)])
    assert "R3" not in {d["rule"] for d in result["decisions"]}


# ---------------- R4: no reference match, find candidates ----------------

def _r4(result: dict) -> list[dict]:
    return [d for d in result["decisions"] if d["rule"] == "R4"]


def test_r4_pairs_the_june_top_up_with_priya_nair(june_result):
    congruit = [d for d in _r4(june_result) if d["verdict"] == "CONGRUIT"]
    assert [(_short(d["bank_id"]), d["firm_id"]) for d in congruit] == [("L8", "CE-2026-06-0007")]


def test_r4_rules_out_the_hart_trust_with_a_reason(june_result):
    discrepat = [d for d in _r4(june_result) if d["verdict"] == "DISCREPAT"]
    assert [(_short(d["bank_id"]), d["firm_id"]) for d in discrepat] == [("L8", "CE-2026-06-0008")]
    assert "Priya Nair" in discrepat[0]["evidence"]["reason"]
    assert "Hart Family Trust" in discrepat[0]["evidence"]["reason"]


def test_r4_records_both_candidates_in_the_evidence(june_result):
    for decision in _r4(june_result):
        assert decision["evidence"]["candidates"] == ["CE-2026-06-0007", "CE-2026-06-0008"]


def test_ruled_out_entry_stays_open_for_the_agent(june_result):
    # DISCREPAT says "not this line"; CE-0008 still needs explaining.
    assert "CE-2026-06-0008" in {item["id"] for item in june_result["unmatched_firm"]}


def test_r4_single_candidate_is_congruit():
    result = _match([_bank(reference="BANK-OWN-REF")], [_firm(reference="FIRM-REF")])
    assert [(d["rule"], d["verdict"]) for d in result["decisions"]] == [("R4", "CONGRUIT")]


def test_r4_needs_exactly_the_same_amount():
    result = _match([_bank(reference=None, amount=Decimal("100.01"))], [_firm(reference=None)])
    assert result["decisions"] == []


def test_r4_needs_the_date_within_tolerance():
    result = _match([_bank(reference=None, date=date(2026, 6, 13))], [_firm(reference=None)])
    assert result["decisions"] == []


def test_r4_known_types_must_agree():
    result = _match([_bank(reference=None, entry_type="DIVIDEND")],
                   [_firm(reference=None, entry_type="SUBSCRIPTION")])
    assert result["decisions"] == []


def test_r4_unknown_bank_type_allows_any_type():
    result = _match([_bank(reference=None, entry_type=None)],
                   [_firm(reference=None, entry_type="SUBSCRIPTION")])
    assert [d["verdict"] for d in result["decisions"]] == ["CONGRUIT"]


def test_r4_two_candidates_and_no_name_is_non_liquet():
    result = _match([_bank(reference=None, description="FASTER PAYMENT")],
                   [_firm("F1", reference=None, party="Priya Nair"),
                    _firm("F2", reference=None, party="Daniel Okoro")])
    assert [d["verdict"] for d in result["decisions"]] == ["NON LIQUET", "NON LIQUET"]
    # Nothing is settled: a person decides.
    assert len(result["unmatched_bank"]) == 1 and len(result["unmatched_firm"]) == 2


def test_r4_name_fitting_two_candidates_is_non_liquet():
    # "HART" fits Amelia Hart and the Hart Family Trust: too weak to choose.
    result = _match([_bank(reference=None, description="FASTER PAYMENT HART")],
                   [_firm("F1", reference=None, party="Amelia Hart"),
                    _firm("F2", reference=None, party="Hart Family Trust")])
    assert {d["verdict"] for d in result["decisions"]} == {"NON LIQUET"}


def test_r4_name_must_be_a_whole_word():
    # "NAIRN" is not "NAIR".
    result = _match([_bank(reference=None, description="PAYMENT NAIRN")],
                   [_firm("F1", reference=None, party="Priya Nair"),
                    _firm("F2", reference=None, party="Daniel Okoro")])
    assert {d["verdict"] for d in result["decisions"]} == {"NON LIQUET"}


# ---------------- R5: settlement after the period ----------------

def _findings_by_rule(result: dict, rule: str) -> list[dict]:
    return [f for f in result["findings"] if f["rule"] == rule]


def test_r5_finds_the_buy_that_settles_in_july(june_result):
    assert [f["firm_ids"] for f in _findings_by_rule(june_result, "R5")] == [["CE-2026-06-0011"]]


def test_r5_finding_is_an_outstanding_payment_adjusting_the_bank(june_result):
    finding = _findings_by_rule(june_result, "R5")[0]
    assert finding["rule"] == "R5"
    assert finding["category"] == "IN_TRANSITU"
    assert finding["type"] == "OUTSTANDING_PAYMENT"
    assert finding["adjusts"] == "bank"
    assert finding["adjustment"] == Decimal("-3717.00")
    assert finding["evidence"]["settlement_date"] == date(2026, 7, 1)
    assert finding["evidence"]["reference"] == "TR-26062901"


def test_r5_finding_waits_for_a_person(june_result):
    finding = _findings_by_rule(june_result, "R5")[0]
    assert finding["status"] == "PROPOSED"
    assert finding["decided_by"] is None


def _settlement(**changes) -> dict:
    """A trade settlement settling 2 July (after June); change only what a test needs."""
    fields = {"reference": "TR-9", "entry_type": "TRADE_SETTLEMENT",
              "amount": Decimal("-500.00"), "expected_date": date(2026, 7, 2)}
    fields.update(changes)
    return _firm(**fields)


def test_r5_settlement_on_the_last_day_is_not_in_transit():
    result = _match([], [_settlement(expected_date=JUNE_END)])
    assert result["findings"] == []
    assert len(result["unmatched_firm"]) == 1


def test_r5_only_applies_to_trade_settlements():
    # A subscription dated next month is something else: the agent's job.
    result = _match([], [_firm(expected_date=date(2026, 7, 2))])
    assert result["findings"] == []


def test_r5_sale_settling_next_month_is_an_outstanding_receipt():
    result = _match([], [_settlement(amount=Decimal("700.00"))])
    assert result["findings"][0]["type"] == "OUTSTANDING_RECEIPT"


def test_r5_entry_with_a_finding_leaves_the_open_list():
    result = _match([], [_settlement()])
    assert result["unmatched_firm"] == []


# ---------------- R2a: withholding tax ----------------

def test_r2a_explains_the_june_dividend_as_withholding_tax(june_result):
    [finding] = _findings_by_rule(june_result, "R2a")
    assert finding["category"] == "OMISSUM"
    assert finding["type"] == "WITHHOLDING_TAX"
    assert finding["firm_ids"] == ["CE-2026-06-0004"]
    assert [_short(b) for b in finding["bank_ids"]] == ["L5"]


def test_r2a_adjusts_the_book_by_the_tax(june_result):
    # 1,500.00 gross, 1,275.00 paid: the firm hasn't recorded 225.00 of tax.
    [finding] = _findings_by_rule(june_result, "R2a")
    assert finding["adjusts"] == "book"
    assert finding["adjustment"] == Decimal("-225.00")
    assert finding["evidence"]["tax"] == Decimal("225.00")
    assert finding["status"] == "PROPOSED"


def _dividend(**changes) -> dict:
    """An overseas dividend of 1,000.00 expected in June; change only what a test needs."""
    fields = {"entry_type": "DIVIDEND", "domicile": "overseas", "amount": Decimal("1000.00")}
    fields.update(changes)
    return _firm(**fields)


def test_r2a_needs_exactly_the_tax_rate():
    exact = _match([_bank(amount=Decimal("850.00"))], [_dividend()])
    off_by_a_penny = _match([_bank(amount=Decimal("850.01"))], [_dividend()])
    assert [f["rule"] for f in exact["findings"]] == ["R2a"]
    assert off_by_a_penny["findings"] == []


def test_r2a_needs_an_overseas_security():
    result = _match([_bank(amount=Decimal("850.00"))], [_dividend(domicile="uk")])
    assert result["findings"] == []


def test_r2a_only_applies_to_dividends():
    result = _match([_bank(amount=Decimal("850.00"))],
                    [_dividend(entry_type="SUBSCRIPTION")])
    assert result["findings"] == []


def test_r2a_still_leaves_the_r2_match_in_place():
    result = _match([_bank(amount=Decimal("850.00"))], [_dividend()])
    assert [(d["rule"], d["verdict"]) for d in result["decisions"]] == [("R2", "CONGRUIT")]