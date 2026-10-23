"""graph_to_json.py: a snapshot as readable JSON, written next to it, never overwritten."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from liquet.graph.build_graph import build_graph, save_snapshot
from liquet.graph.graph_to_json import write_graph_json
from liquet.pipeline.run_month import main as run_month

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def written(tmp_path):
    run = run_month(SOURCES, tmp_path / "runs", RUN_AT)["folder"]
    snapshot = save_snapshot(build_graph(run), run, "rules", RUN_AT)
    return snapshot, write_graph_json(snapshot)


def test_the_file_sits_next_to_its_snapshot_and_is_never_overwritten(written):
    snapshot, file = written
    assert file == snapshot.with_name(snapshot.name + ".json")
    with pytest.raises(FileExistsError):
        write_graph_json(snapshot)


def test_nodes_by_type_and_edges_by_layer(written):
    content = json.loads(written[1].read_text(encoding="utf-8"))
    assert content["counts"]["nodes"] == 54 and content["counts"]["edges"] == 94
    assert len(content["nodes"]["BankEntry"]) == 12
    assert {e["to"] for e in content["edges"]["PROPOSED_BY"]} == {"rule:R5", "rule:R2a"}


def test_money_stays_exact_text(written):
    content = json.loads(written[1].read_text(encoding="utf-8"))
    r2a = next(f for f in content["nodes"]["Finding"] if f["properties"]["rule"] == "R2a")
    assert r2a["properties"]["adjustment"] == "-225.00"