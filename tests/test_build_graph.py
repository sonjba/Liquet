import json
import shutil
from datetime import datetime, timedelta, timezone
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
    ("BankEntry", 12), ("Finding", 2), ("Actor", 2),
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


@pytest.mark.parametrize("node_type", [
    "Client", "Portfolio", "Account", "AccountBalance", "Security", "Trade", "CashMovement"])
def test_every_firm_node_says_where_it_came_from(g, node_type):
    sources = [n.properties.get("source") for n in g.nodes if n.node_type == node_type]
    assert sources and all(sources)


def test_a_movement_traces_back_to_its_place_in_the_firm_data(g):
    assert g.node("CE-2026-06-0008").properties.get("source").startswith("portfolios/PF-CL-005/")


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
    assert "withholding tax" in tax.properties.get("explanation")
    assert {n.name for n in tax.out_neighbours} == {
        "CE-2026-06-0004", _line(5), "ACC-KRW-CASH-01:2026-06", "rule:R2a"}


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
    assert build_graph(run_folder).count_nodes() == 54


def test_a_run_saved_before_data_was_stored_says_so(june_run, tmp_path):
    old = tmp_path / "old-run"
    shutil.copytree(june_run, old)
    shutil.rmtree(old / "liquet_format")
    with pytest.raises(FileNotFoundError, match="no liquet_format/ folder"):
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

# ---------------- who proposed, and a person's decisions ----------------

def test_each_finding_points_to_the_rule_that_proposed_it(g):
    proposer = g.edge(finding_node_id(RUN_ID, "R5:CE-2026-06-0011"), "rule:R5")
    assert proposer.layer_names == ["PROPOSED_BY"]
    assert g.node("rule:R5").properties.get("kind") == "rule"


@pytest.fixture(scope="module")
def reviewed(june_run, tmp_path_factory):
    """A copy of the June run where sonja approved R5 and rejected R2a, an hour apart."""
    from decide import record
    folder = tmp_path_factory.mktemp("reviewed") / "run-001"
    shutil.copytree(june_run, folder)
    record(folder, "APPROVED", "R5:CE-2026-06-0011", "sonja", REVIEW_AT, "CONFIRMED")
    record(folder, "REJECTED", "R2a:CE-2026-06-0004", "sonja", REVIEW_AT + timedelta(hours=1),
           "NEEDS_EVIDENCE", "check the tax rate with the custodian")
    return build_graph(folder)


REVIEW_AT = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)


def test_a_reviewed_run_adds_decisions_and_the_person(reviewed):
    assert (reviewed.count_nodes(), reviewed.count_edges()) == (57, 98)
    assert _count(reviewed, "Decision") == 2
    assert reviewed.node("person:sonja").properties.get("kind") == "person"


def test_a_decision_says_what_why_who_and_about_what(reviewed):
    decision = reviewed.node(f"{RUN_ID}:D2")
    assert decision.properties.get("kind") == "REJECTED"
    assert decision.properties.get("reason_code") == "NEEDS_EVIDENCE"
    assert decision.properties.get("reason") == "check the tax rate with the custodian"
    assert reviewed.has_edge(f"{RUN_ID}:D2", finding_node_id(RUN_ID, "R2a:CE-2026-06-0004"))
    assert reviewed.edge(f"{RUN_ID}:D2", "person:sonja").layer_names == ["MADE_BY"]


def test_the_graph_remembers_the_status_before_and_after_the_decision(reviewed):
    finding = finding_node_id(RUN_ID, "R5:CE-2026-06-0011")
    before = reviewed.before(REVIEW_AT)
    assert before.node(finding).properties.get("status") == "PROPOSED"
    assert not before.has_node(f"{RUN_ID}:D1")              # not decided yet at that moment
    assert reviewed.node(finding).properties.get("status") == "APPROVED"


def test_a_review_snapshot_is_saved_next_to_the_rules_one(g, reviewed, tmp_path):
    rules = save_snapshot(g, tmp_path, "rules", RUN_AT)
    review = save_snapshot(reviewed, tmp_path, "review", REVIEW_AT)
    assert load_snapshot(rules).count_nodes() == 54         # the rules version, unchanged
    assert describe(load_snapshot(review)) == describe(reviewed)


def test_a_proposal_is_a_finding_with_its_proposer(june_run, tmp_path):
    from decide import record
    from propose import record_proposal
    folder = tmp_path / "run-001"
    shutil.copytree(june_run, folder)
    l12 = "ACC-KRW-CASH-01:2026-06:L12"
    record_proposal(folder, [l12], "OMISSUM", "BANK_FEE", "book", "-45.00",
                    "June custody fee, not yet booked.", "quaestor", "agent", REVIEW_AT,
                    model="claude-sonnet-5-5")
    record(folder, "APPROVED", "P1", "sonja", REVIEW_AT + timedelta(hours=1), "CONFIRMED")
    g = build_graph(folder)
    from liquet.store.run_store import load_run
    node = finding_node_id(load_run(folder)["run"]["run_id"], "P1")
    assert g.node(node).node_type == "Finding"
    assert g.node(node).properties.get("model") == "claude-sonnet-5-5"
    assert [e.dst.name for e in g.valid_layers(["PROPOSED_BY"]).node(node).out_edges] == ["agent:quaestor"]
    assert [e.dst.name for e in g.valid_layers(["EXPLAINS_LINE"]).node(node).out_edges] == [l12]
    assert g.before(REVIEW_AT + timedelta(minutes=30)).node(node).properties.get("status") == "PROPOSED"
    assert g.node(node).properties.get("status") == "APPROVED"


def test_an_investigation_records_what_claude_was_asked_and_what_it_led_to(june_run, tmp_path):
    from propose import record_proposal
    from liquet.store.run_store import load_run
    folder = tmp_path / "run-001"
    shutil.copytree(june_run, folder)
    l12, ce8 = "ACC-KRW-CASH-01:2026-06:L12", "CE-2026-06-0008"
    record_proposal(folder, [l12], "OMISSUM", "BANK_FEE", "book", "-45.00",
                    "June custody fee, not yet booked.", "quaestor", "agent", REVIEW_AT,
                    model="claude-sonnet-5-5")
    calls = [  # as try_claude.py logs them: one proposal, one NON_LIQUET
        {"at": REVIEW_AT.isoformat(), "item_id": l12, "model": "claude-sonnet-5-5",
         "question": "Facts gathered by Liquet: ...", "outcome": "saved as P1", "proposal_id": "P1",
         "answer": {"answer": "PROPOSAL", "explanation": "June custody fee, not yet booked."},
         "input_tokens": 1031, "output_tokens": 180, "stop_reason": "end_turn"},
        {"at": REVIEW_AT.isoformat(), "item_id": ce8, "model": "claude-sonnet-5-5",
         "question": "Facts gathered by Liquet: ...", "outcome": "NON_LIQUET, nothing proposed",
         "proposal_id": None,
         "answer": {"answer": "NON_LIQUET", "explanation": "Needs next month's statement."},
         "input_tokens": 1096, "output_tokens": 236, "stop_reason": "end_turn"}]
    (folder / "investigations.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in calls), encoding="utf-8")

    g = build_graph(folder)
    run_id = load_run(folder)["run"]["run_id"]
    first, second = f"{run_id}:I1", f"{run_id}:I2"
    assert g.node(first).node_type == "Investigation"
    assert g.node(first).properties.get("input_tokens") == 1031
    assert [e.dst.name for e in g.valid_layers(["INVESTIGATED"]).node(first).out_edges] == [l12]
    assert [e.dst.name for e in g.valid_layers(["RUN_BY"]).node(first).out_edges] == ["agent:quaestor"]
    assert [e.dst.name for e in g.valid_layers(["PRODUCED"]).node(first).out_edges] == [
        finding_node_id(run_id, "P1")]
    # a NON_LIQUET is kept in the graph too, and led to nothing
    assert g.node(second).properties.get("answer") == "NON_LIQUET"
    assert [e.dst.name for e in g.valid_layers(["INVESTIGATED"]).node(second).out_edges] == [ce8]
    assert list(g.valid_layers(["PRODUCED"]).node(second).out_edges) == []