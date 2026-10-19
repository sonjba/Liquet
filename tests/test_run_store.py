import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from run_month import ingest
from liquet.store.run_store import (InputsChangedError, fingerprints, load_liquet_format, load_run,
                       new_run_folder, next_run_folder, run_folder_name, save_liquet_format,
                       save_received, save_results)

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}


@pytest.fixture(scope="module")
def june_data():
    """June in Liquet's format, as the door hands it over. Shared: don't change it."""
    return ingest(SOURCES)


@pytest.fixture
def header(june_data):
    return june_data["bank_statement"]["header"]


# ---------------- the run folder ----------------

def test_folder_is_named_by_account_and_month_without_a_colon(header):
    assert run_folder_name(header) == "ACC-KRW-CASH-01_2026-06"


def test_first_run_of_a_month_is_run_001_and_the_next_is_run_002(header, tmp_path):
    first = new_run_folder(tmp_path, header)
    second = new_run_folder(tmp_path, header)
    assert first == tmp_path / "ACC-KRW-CASH-01_2026-06" / "run-001"
    assert second.name == "run-002"


def test_next_run_number_follows_the_highest_not_the_count(tmp_path):
    # run-001 was deleted by hand; run-002 remains: the next is run-003, not run-002.
    (tmp_path / "run-002").mkdir()
    (tmp_path / "notes").mkdir()
    assert next_run_folder(tmp_path).name == "run-003"


# ---------------- received ----------------

def test_received_files_are_exact_copies_named_by_role(tmp_path):
    received = save_received(tmp_path, SOURCES, fingerprints(SOURCES))
    assert sorted(p.name for p in (tmp_path / "received").iterdir()) == [
        "accounts.json", "header.json", "lines.csv", "portfolios.json"]
    assert (tmp_path / "received" / "lines.csv").read_bytes() == SOURCES["lines"].read_bytes()
    assert received["lines"]["file"] == "received/lines.csv"
    assert received["lines"]["original_path"] == str(SOURCES["lines"])
    assert len(received["lines"]["sha256"]) == 64


def test_a_file_that_changed_after_it_was_read_stops_the_run(tmp_path):
    lines = tmp_path / "bank_statement.csv"
    lines.write_bytes(SOURCES["lines"].read_bytes())
    sources = dict(SOURCES, lines=lines)
    read = fingerprints(sources)
    lines.write_bytes(lines.read_bytes() + b"\n")          # changed between read and copy
    (tmp_path / "run").mkdir()
    with pytest.raises(InputsChangedError, match="lines"):
        save_received(tmp_path / "run", sources, read)


# ---------------- data ----------------

def test_data_is_three_liquet_files(june_data, tmp_path):
    save_liquet_format(tmp_path, june_data)
    assert sorted(p.name for p in (tmp_path / "liquet_format").iterdir()) == [
        "bank_statement.json", "firm_canonical.json", "firm_cash_entries.json"]


def test_data_loads_back_exactly_as_it_was_saved(june_data, tmp_path):
    save_liquet_format(tmp_path, june_data)
    assert load_liquet_format(tmp_path) == june_data


def test_money_and_dates_come_back_as_decimal_and_date(june_data, tmp_path):
    save_liquet_format(tmp_path, june_data)
    statement = load_liquet_format(tmp_path)["bank_statement"]
    assert statement["header"]["closing_balance"] == Decimal("285378.57")
    assert statement["header"]["period_end"] == date(2026, 6, 30)
    line = statement["lines"][1]
    assert (line["date"], line["amount"], line["paid_in"]) == (
        date(2026, 6, 3), Decimal("-4852.40"), None)


def test_money_is_saved_as_text(june_data, tmp_path):
    save_liquet_format(tmp_path, june_data)
    saved = json.loads((tmp_path / "liquet_format" / "bank_statement.json").read_text())
    assert saved["lines"][1]["amount"] == "-4852.40"


def test_a_run_without_data_says_so(tmp_path):
    with pytest.raises(FileNotFoundError, match="no liquet_format/ folder"):
        load_liquet_format(tmp_path)


# ---------------- results ----------------

def _result():
    return {"decisions": [{"bank_id": "B", "firm_id": "F",
                           "differences": [{"difference": Decimal("-225.00")}]}],
            "findings": [{"finding_id": "R5:F", "status": "PROPOSED"}],
            "unmatched_bank": [], "unmatched_firm": [{"id": "F2"}]}


def test_results_and_run_json_are_written(header, tmp_path):
    folder = new_run_folder(tmp_path, header)
    save_results(folder, header, _result(), RUN_AT, received={"lines": {}}, stages=["a", "b"])
    run = load_run(folder)
    info = run["run"]
    assert info["run_id"] == "ACC-KRW-CASH-01_2026-06/run-001"
    assert info["statement_id"] == "ACC-KRW-CASH-01:2026-06"
    assert info["period_end"] == "2026-06-30"
    assert info["run_at"] == "2026-07-02T09:30:00+00:00"
    assert info["stages"] == ["a", "b"]
    assert info["counts"] == {"decisions": 1, "findings": 1, "leftover_bank": 0,
                              "leftover_firm": 1}
    assert run["decisions"][0]["differences"][0]["difference"] == "-225.00"
    assert run["findings"][0]["proposed_at"] == "2026-07-02T09:30:00+00:00"


def test_saving_does_not_change_the_result_in_memory(header, tmp_path):
    result = _result()
    save_results(tmp_path, header, result, RUN_AT, received={}, stages=[])
    assert "proposed_at" not in result["findings"][0]


def test_a_run_without_run_json_did_not_finish(tmp_path):
    with pytest.raises(FileNotFoundError, match="did not finish"):
        load_run(tmp_path)


def test_results_are_never_overwritten(header, tmp_path):
    save_results(tmp_path, header, _result(), RUN_AT, received={}, stages=[])
    with pytest.raises(FileExistsError, match="never overwritten"):
        save_results(tmp_path, header, _result(), RUN_AT, received={}, stages=[])


def test_something_json_cannot_hold_is_refused(header, tmp_path):
    bad = dict(_result(), decisions=[{"oops": {1, 2}}])
    with pytest.raises(TypeError, match="can't save set"):
        save_results(tmp_path, header, bad, RUN_AT, received={}, stages=[])
