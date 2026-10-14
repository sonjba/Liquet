import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bank_prepare import bank_to_item
from bank_reader import read_statement
from firm_connector import FirmFileConnector
from firm_prepare import domiciles_by_ticker, firm_to_item, parties_by_portfolio
from match import match
from run_store import load_run, run_folder_name, save_run

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)
INPUTS = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
          "accounts": JUNE / "firm" / "accounts.json",
          "portfolios": JUNE / "firm" / "portfolios.json"}


@pytest.fixture(scope="module")
def june_month():
    """June's month dict, as run_month.main() builds it (only the parts save_run needs)."""
    header, lines = read_statement(INPUTS["header"], INPUTS["lines"])
    firm = FirmFileConnector(INPUTS["accounts"], INPUTS["portfolios"])
    trades = {t["trade_id"]: t for t in firm.canonical["trades"]}
    parties = parties_by_portfolio(firm.canonical)
    domiciles = domiciles_by_ticker(firm.canonical)
    entries = firm.get_cash_entries(header["account_id"], header["period_start"], header["period_end"])
    result = match([bank_to_item(line) for line in lines],
                   [firm_to_item(e, trades, parties, domiciles) for e in entries],
                   period_end=header["period_end"])
    return {"header": header, "result": result}


@pytest.fixture
def saved(june_month, tmp_path):
    folder = save_run(june_month, tmp_path, run_at=RUN_AT, inputs=INPUTS)
    return folder, load_run(folder)


def test_folder_is_named_by_account_and_month_without_a_colon(june_month):
    assert run_folder_name(june_month["header"]) == "ACC-KRW-CASH-01_2026-06"


def test_the_four_files_are_written(saved):
    folder, _ = saved
    assert sorted(p.name for p in folder.iterdir()) == [
        "decisions.json", "findings.json", "leftovers.json", "run.json"]


def test_run_json_says_when_what_and_from_which_files(saved):
    _, run = saved
    info = run["run"]
    assert info["statement_id"] == "ACC-KRW-CASH-01:2026-06"
    assert info["period_end"] == "2026-06-30"
    assert info["run_at"] == "2026-07-02T09:30:00+00:00"
    assert set(info["inputs"]) == {"header", "lines", "accounts", "portfolios"}
    assert all(len(f["sha256"]) == 64 for f in info["inputs"].values())
    assert info["counts"] == {"decisions": 15, "findings": 2,
                              "leftover_bank": 2, "leftover_firm": 1}


def test_money_is_saved_as_exact_text(saved):
    _, run = saved
    dividend = next(d for d in run["decisions"] if d["rule"] == "R2")
    assert dividend["differences"][0]["difference"] == "-225.00"


def test_findings_are_stamped_with_created_at(saved):
    _, run = saved
    assert [f["finding_id"] for f in run["findings"]] == ["R2a:CE-2026-06-0004",
                                                         "R5:CE-2026-06-0011"]
    assert all(f["created_at"] == "2026-07-02T09:30:00+00:00" for f in run["findings"])
    assert all(f["status"] == "PROPOSED" for f in run["findings"])


def test_leftovers_are_what_the_agent_gets(saved):
    _, run = saved
    assert [i["id"].split(":")[-1] for i in run["leftovers"]["bank"]] == ["L12", "L13"]
    assert [i["id"] for i in run["leftovers"]["firm"]] == ["CE-2026-06-0008"]


def test_saving_does_not_change_the_result_in_memory(june_month, tmp_path):
    save_run(june_month, tmp_path, run_at=RUN_AT, inputs=INPUTS)
    assert "created_at" not in june_month["result"]["findings"][0]


def test_a_saved_run_is_never_overwritten(june_month, tmp_path):
    save_run(june_month, tmp_path, run_at=RUN_AT, inputs=INPUTS)
    with pytest.raises(FileExistsError, match="never overwritten"):
        save_run(june_month, tmp_path, run_at=RUN_AT, inputs=INPUTS)


def test_same_input_and_time_give_the_same_files(june_month, tmp_path):
    first = save_run(june_month, tmp_path / "a", run_at=RUN_AT, inputs=INPUTS)
    second = save_run(june_month, tmp_path / "b", run_at=RUN_AT, inputs=INPUTS)
    for name in ("run.json", "decisions.json", "findings.json", "leftovers.json"):
        assert (first / name).read_text() == (second / name).read_text()


def test_a_changed_input_file_changes_its_fingerprint(june_month, tmp_path):
    copy = tmp_path / "bank_statement.csv"
    copy.write_bytes(INPUTS["lines"].read_bytes() + b"\n")
    folder = save_run(june_month, tmp_path / "runs", run_at=RUN_AT,
                      inputs=dict(INPUTS, lines=copy))
    saved_hash = json.loads((folder / "run.json").read_text())["inputs"]["lines"]["sha256"]
    original = save_run(june_month, tmp_path / "runs2", run_at=RUN_AT, inputs=INPUTS)
    original_hash = json.loads((original / "run.json").read_text())["inputs"]["lines"]["sha256"]
    assert saved_hash != original_hash


def test_something_json_cannot_hold_is_refused(june_month, tmp_path):
    bad = {"header": june_month["header"],
           "result": dict(june_month["result"], decisions=[{"oops": {1, 2}}])}
    with pytest.raises(TypeError, match="can't save set"):
        save_run(bad, tmp_path, run_at=RUN_AT, inputs=INPUTS)