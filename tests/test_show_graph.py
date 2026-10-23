"""show_graph.py: a picture of a saved snapshot, written next to it, never overwritten."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from liquet.graph.build_graph import build_graph, save_snapshot
from run_month import main as run_month
from liquet.graph.show_graph import short_label, write_graph_page

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("node_id, node_type, properties, label", [
    ("ACC-KRW-CASH-01:2026-06:L8", "BankEntry", {}, "L8"),
    ("X_2026-06/run-001:R5:CE-2026-06-0011", "Finding", {"finding_id": "R5:CE-2026-06-0011"},
     "R5 finding"),
    ("X_2026-06/run-001:D2", "Decision", {"kind": "REJECTED"}, "D2 REJECTED"),
    ("person:sonja", "Actor", {}, "person sonja"),
])
def test_short_labels(node_id, node_type, properties, label):
    assert short_label(node_id, node_type, properties) == label


def test_the_page_sits_next_to_its_snapshot_and_is_never_overwritten(tmp_path):
    run = run_month(SOURCES, tmp_path / "runs", RUN_AT)["folder"]
    snapshot = save_snapshot(build_graph(run), run, "rules", RUN_AT)
    page = write_graph_page(snapshot)
    assert page == snapshot.with_name(snapshot.name + ".html")
    assert "R5 finding" in page.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError, match="never overwritten"):
        write_graph_page(snapshot)
