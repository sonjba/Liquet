import json
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import run_month
from build_graph import build_graph, describe, finding_node_id, load_snapshot, save_snapshot

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)
RUN_ID = "ACC-KRW-CASH-01_2026-06/run-001"


JUNE_FILES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
              "accounts": JUNE / "firm" / "accounts.json",
              "portfolios": JUNE / "firm" / "portfolios.json"}


def _copy_june_files(folder: Path) -> dict[str, Path]:
    """Copy June's four input files (contents only) into folder; return their paths.
    copyfile copies no Windows attributes, so the copies can be changed and deleted."""
    folder.mkdir(parents=True)
    copies = {}
    for name, path in JUNE_FILES.items():
        copies[name] = folder / path.name
        shutil.copyfile(path, copies[name])
    return copies


def _save_june_run(sources: dict[str, Path], runs_dir: Path) -> Path:
    """Run June through the whole pipeline and return the run folder."""
    return run_month.main(sources, runs_dir, RUN_AT)["folder"]


@pytest.fixture(scope="module")
def june_run(tmp_path_factory):
    return _save_june_run(JUNE_FILES, tmp_path_factory.mktemp("runs"))


@pytest.fixture(scope="module")
def g(june_run):
    return build_graph(june_run)


def _count(graph, node_type: str) -> int:
    return sum(1 for n in graph.nodes if n.node_type == node_type)


def _line(n: int) -> str:
    return f"ACC-KRW-CASH-01:2026-06:L{n}"


# ---------------- what is in the graph ----------------

@pytest.mark.parametrize("node_type, expected", [
    ("Client", 5), ("Portfolio", 5), ("Account", 1), ("AccountBalance", 1),
    ("Security", 4), ("Trade", 5), ("CashMovement", 16), ("BankStatement", 1),
    ("BankEntry", 12), ("Finding", 2),
])
def test_june_has_every_record_as_a_node(g, node_type, expected):
    assert _count(g, node_type) == expected


def test_amounts_stay_exact_decimals(g):
    assert g.node("CE-2026-06-0002").properties.get("amount") == Decimal("-4852.40")
    assert g.node(_line(3)).properties.get("amount") == Decimal("-4852.40")


def test_the_graph_answers_whose_movement_this_is(g):
    # CE-0008 -> its portfolio -> the client who owns it.
    entry = g.node("CE-2026-06-0008")
    [portfolio] = [n for n in entry.in_neighbours if n.node_type == "Portfolio"]
    [client] = [n for n in portfolio.in_neighbours if n.node_type == "Client"]
    assert (portfolio.name, client.properties.get("name")) == ("PF-CL-005", "Hart Family Trust")


def test_dividend_points_to_its_overseas_security(g):
    [security] = [n for n in g.node("CE-2026-06-0004").out_neighbours if n.node_type == "Security"]
    assert (security.name, security.properties.get("domicile")) == ("ATIT", "overseas")


# ---------------- decisions ----------------

def test_every_decision_is_a_matched_to_edge(g):
    verdicts = [e.properties.get("verdict") for e in g.layer("MATCHED_TO").edges]
    assert len(verdicts) == 15
    assert sorted(set(verdicts)) == ["CONGRUIT", "DISCREPAT"]
    assert verdicts.count("DISCREPAT") == 1


def test_ruled_out_candidate_keeps_its_reason(g):
    edge = g.edge(_line(8), "CE-2026-06-0008")
    assert edge.properties.get("verdict") == "DISCREPAT"
    assert "Priya Nair" in json.loads(edge.properties.get("evidence"))["reason"]


def test_decision_differences_are_kept_exactly(g):
    differences = json.loads(g.edge(_line(5), "CE-2026-06-0004").properties.get("differences"))
    assert differences[0]["difference"] == "-225.00"


# ---------------- findings ----------------

def test_findings_link_to_what_they_explain_and_to_their_month(g):
    tax = g.node(finding_node_id(RUN_ID, "R2a:CE-2026-06-0004"))
    assert tax.properties.get("type") == "WITHHOLDING_TAX"
    assert tax.properties.get("adjustment") == Decimal("-225.00")
    assert tax.properties.get("status") == "PROPOSED"
    assert {n.name for n in tax.out_neighbours} == {
        "CE-2026-06-0004", _line(5), "ACC-KRW-CASH-01:2026-06"}


def test_finding_names_carry_the_run(g):
    names = sorted(n.name for n in g.nodes if n.node_type == "Finding")
    assert names == [f"{RUN_ID}:R2a:CE-2026-06-0004", f"{RUN_ID}:R5:CE-2026-06-0011"]


# ---------------- time ----------------

def test_nothing_was_decided_before_the_run(g):
    assert g.before("2026-07-02").layer("MATCHED_TO").count_edges() == 0
    assert g.before("2026-07-03").layer("MATCHED_TO").count_edges() == 15


def test_records_sit_at_their_own_dates(g):
    first_half = g.window("2026-06-01", "2026-06-16")
    entries = {n.name for n in first_half.nodes if n.node_type == "CashMovement"}
    assert entries == {f"CE-2026-06-000{i}" for i in range(1, 7)}


def test_settlement_after_the_month_is_placed_in_july(g):
    # CE-0011's trade settles 1 July: not yet settled at the end of June.
    assert not g.before("2026-07-01").has_edge("TR-26062901", "CE-2026-06-0011")
    assert g.before("2026-07-02").has_edge("TR-26062901", "CE-2026-06-0011")


# ---------------- the graph is built from the run folder only ----------------

def test_files_changed_after_the_run_do_not_change_its_graph(tmp_path):
    sources = _copy_june_files(tmp_path / "inputs")
    run_folder = _save_june_run(sources, tmp_path / "runs")
    before = describe(build_graph(run_folder))
    sources["lines"].write_text("not even a statement any more\n")
    sources["accounts"].unlink()
    sources["portfolios"].unlink()
    assert describe(build_graph(run_folder)) == before


def test_the_run_folder_alone_is_enough(tmp_path):
    # Delete every original file: the run folder still builds the whole graph.
    sources = _copy_june_files(tmp_path / "inputs")
    run_folder = _save_june_run(sources, tmp_path / "runs")
    for path in sources.values():
        path.unlink()
    assert build_graph(run_folder).count_nodes() == 52


def test_a_run_saved_before_data_was_stored_says_so(june_run, tmp_path):
    old = tmp_path / "old-run"
    shutil.copytree(june_run, old)
    shutil.rmtree(old / "data")
    with pytest.raises(FileNotFoundError, match="no data/ folder"):
        build_graph(old)


# ---------------- snapshots ----------------

def test_snapshot_loads_back_the_same_graph(g, tmp_path):
    folder = save_snapshot(g, tmp_path, "rules", RUN_AT)
    assert folder.name == "2026-07-02T09-30-00_rules"
    assert describe(load_snapshot(folder)) == describe(g)


def test_snapshot_keeps_exact_money(g, tmp_path):
    reloaded = load_snapshot(save_snapshot(g, tmp_path, "rules", RUN_AT))
    assert reloaded.node("CE-2026-06-0011").properties.get("amount") == Decimal("-3717.00")


def test_a_snapshot_that_loses_something_stops_the_save(g, tmp_path, monkeypatch):
    # Pretend the file format dropped data (as save_to_file drops Decimals).
    import build_graph
    monkeypatch.setattr(build_graph, "load_snapshot", lambda folder: build_graph.Graph())
    with pytest.raises(ValueError, match="does not load back the same graph"):
        save_snapshot(g, tmp_path, "rules", RUN_AT)


def test_a_snapshot_is_never_overwritten(g, tmp_path):
    save_snapshot(g, tmp_path, "rules", RUN_AT)
    with pytest.raises(FileExistsError, match="never overwritten"):
        save_snapshot(g, tmp_path, "rules", RUN_AT)


def test_rebuilding_gives_the_same_graph(june_run, g):
    assert describe(build_graph(june_run)) == describe(g)