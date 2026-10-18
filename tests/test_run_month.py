"""The whole month, stage by stage: receive, ingest, store, prepare, match,
check, save. Matching must use the data read back from the run folder."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import run_month
from run_store import load_liquet_format, load_run

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}


@pytest.fixture(scope="module")
def june(tmp_path_factory):
    return run_month.main(SOURCES, tmp_path_factory.mktemp("runs"), RUN_AT)


def test_a_run_folder_holds_received_data_and_results(june):
    folder = june["folder"]
    assert folder.name == "run-001"
    assert sorted(p.name for p in folder.iterdir()) == [
        "decisions.json", "findings.json", "leftovers.json", "liquet_format", "received",
        "run.json"]


def test_run_json_lists_the_stages_in_order(june):
    run = load_run(june["folder"])["run"]
    assert run["stages"] == ["receive", "ingest", "store", "bring_forward", "prepare", "match",
                             "check", "save"]
    assert set(run["received"]) == {"header", "lines", "accounts", "portfolios"}


def test_june_result_is_unchanged(june):
    run = load_run(june["folder"])["run"]
    assert run["counts"] == {"decisions": 15, "findings": 2,
                             "leftover_bank": 2, "leftover_firm": 1}


def test_items_come_from_the_stored_data(june):
    stored = load_liquet_format(june["folder"])
    assert [i["id"] for i in june["bank_items"]] == [
        line["line_id"] for line in stored["bank_statement"]["lines"]]
    assert [i["id"] for i in june["firm_items"]] == [
        e["entry_id"] for e in stored["firm_cash_entries"]]


def test_matching_works_on_the_data_read_back_from_the_run_folder(tmp_path, monkeypatch):
    # Keep hold of what load_liquet_format returned: the month must be built from
    # that object, not from what ingest produced in memory.
    loaded = []
    monkeypatch.setattr(run_month, "load_liquet_format",
                        lambda folder: loaded.append(load_liquet_format(folder)) or loaded[-1])
    month = run_month.main(SOURCES, tmp_path, RUN_AT)
    [data] = loaded
    assert month["header"] is data["bank_statement"]["header"]
    assert month["bank_items"][0]["date"] is data["bank_statement"]["lines"][0]["date"]


def test_if_stored_data_does_not_read_back_the_same_the_run_stops(tmp_path, monkeypatch):
    def lossy_load(folder):
        data = load_liquet_format(folder)
        data["bank_statement"]["lines"].pop()
        return data

    monkeypatch.setattr(run_month, "load_liquet_format", lossy_load)
    with pytest.raises(ValueError, match="does not give the same data"):
        run_month.main(SOURCES, tmp_path, RUN_AT)
    [folder] = (tmp_path / "ACC-KRW-CASH-01_2026-06").iterdir()
    assert not (folder / "run.json").exists()       # an unfinished run says so
    assert (folder / "liquet_format" / "bank_statement.json").exists()   # but its data is kept


def test_running_a_month_again_keeps_the_first_run(tmp_path):
    first = run_month.main(SOURCES, tmp_path, RUN_AT)["folder"]
    before = {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()}
    second = run_month.main(SOURCES, tmp_path, RUN_AT)["folder"]
    assert second.name == "run-002"
    assert {p.relative_to(first): p.read_bytes()
            for p in first.rglob("*") if p.is_file()} == before


def test_same_input_and_time_give_the_same_files(tmp_path):
    a = run_month.main(SOURCES, tmp_path / "a", RUN_AT)["folder"]
    b = run_month.main(SOURCES, tmp_path / "b", RUN_AT)["folder"]
    for name in ("decisions.json", "findings.json", "leftovers.json",
                 "liquet_format/bank_statement.json", "liquet_format/firm_canonical.json",
                 "liquet_format/firm_cash_entries.json"):
        assert (a / name).read_text() == (b / name).read_text()
    run_a, run_b = (json.loads((f / "run.json").read_text()) for f in (a, b))
    assert run_a["counts"] == run_b["counts"] and run_a["run_id"] == run_b["run_id"]
