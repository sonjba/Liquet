"""Build Liquet's temporal graph from a saved run, and save checked snapshots of it.

The run folder is the source of truth; the graph is rebuilt from it, and
from nothing else:

  1. Read the run's results (run_store.load_run) and its Liquet-format data
     (run_store.load_data: the data/ folder written before matching).
  2. Add every record at its own time (when the money moved), every decision
     and finding at the run's time (when Liquet decided).

It never opens the received files and never imports the door (readers,
connectors, mappings): a change in how a bank or firm writes its files can't
change the graph of a run that has already happened.

Node types and edge layers follow docs/graph_map.yaml.

Times
  - Records: their own dates (a cash entry's date, a bank line's date,
    a trade's trade and settlement dates, a balance's as_of).
  - Clients, portfolios, accounts, securities and the links between them have
    no date of their own. They are placed on the day before the period starts
    (for June: 31 May), meaning "already known when the month began".
  - Decisions (MATCHED_TO) and findings: run_at, from run.json.

Lineage
  Every firm node carries `source`: where in the firm's data the record came
  from (e.g. portfolios/PF-CL-001/cash_movements/0), so any node can be traced
  back to the received file. A client or security the firm copies into
  several places keeps the first copy's source.

Property values
  Raphtory fixes each property's type the first time it sees it, so every
  property keeps one type everywhere: money is Decimal, dates are text
  ("2026-06-03"), ids and words are text. Nested details (a decision's
  differences and evidence, a finding's evidence) are stored as JSON text.

Snapshots
  save_snapshot() writes the graph as Parquet into the run folder and loads it
  straight back to check nothing was lost. (Raphtory 0.17's save_to_file drops
  Decimal properties without an error; Parquet keeps them.) A snapshot is never
  overwritten.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from raphtory import Graph

from firm_prepare import firm_items
from run_store import _to_text, load_data, load_run


# ---------------- building ----------------

def build_graph(run_folder: Path) -> Graph:
    """Build the graph for one saved run."""
    saved = load_run(run_folder)
    run = saved["run"]
    stored = load_data(run_folder)
    header = stored["bank_statement"]["header"]
    data = {"header": header,
            "lines": stored["bank_statement"]["lines"],
            "canonical": stored["firm_canonical"],
            "entries": stored["firm_cash_entries"],
            "firm_items": firm_items(stored["firm_canonical"], stored["firm_cash_entries"])}
    run_at = datetime.fromisoformat(run["run_at"])
    known_from = header["period_start"] - timedelta(days=1)

    g = Graph()
    _add_firm(g, data, known_from)
    _add_bank(g, data)
    _add_decisions(g, saved["decisions"], run_at, run["run_id"])
    _add_findings(g, saved["findings"], run)
    return g


def _add_firm(g: Graph, data: dict, known_from: date) -> None:
    canonical = data["canonical"]
    account_id = data["header"]["account_id"]

    for a in canonical["accounts"]:
        g.add_node(known_from, a["account_id"], node_type="Account",
                   properties={"name": a["account_name"], "custodian": a["custodian"],
                               "currency": a["currency"], "source": a["source"]})
    for b in canonical["account_balances"]:
        balance_id = f"{b['account_id']}:balance:{b['as_of']}"
        g.add_node(b["as_of"], balance_id, node_type="AccountBalance",
                   properties={"as_of": b["as_of"], "balance": Decimal(b["balance"]),
                               "source": b["source"]})
        g.add_edge(b["as_of"], b["account_id"], balance_id, layer="HAS_BALANCE")
    for c in canonical["clients"]:
        g.add_node(known_from, c["client_id"], node_type="Client",
                   properties={"name": c["name"], "client_type": c["client_type"],
                               "source": c["source"]})
    for p in canonical["portfolios"]:
        g.add_node(known_from, p["portfolio_id"], node_type="Portfolio",
                   properties={"source": p["source"]})
        g.add_edge(known_from, p["client_id"], p["portfolio_id"], layer="OWNS_PORTFOLIO")
        g.add_edge(known_from, p["portfolio_id"], p["account_id"], layer="USES_ACCOUNT")
    for s in canonical["securities"]:
        g.add_node(known_from, s["ticker"], node_type="Security",
                   properties={"name": s["name"], "security_type": s["security_type"],
                               "domicile": s["domicile"], "source": s["source"]})
    for t in canonical["trades"]:
        g.add_node(t["trade_date"], t["trade_id"], node_type="Trade",
                   properties={"side": t["side"], "trade_date": t["trade_date"],
                               "settlement_date": t["settlement_date"],
                               "quantity": t["quantity"], "price": Decimal(t["price"]),
                               "costs": Decimal(t["costs"]),
                               "settlement_amount": Decimal(t["settlement_amount"]),
                               "source": t["source"]})
        g.add_edge(t["trade_date"], t["portfolio_id"], t["trade_id"], layer="HAS_TRADE")
        g.add_edge(t["trade_date"], t["trade_id"], t["ticker"], layer="IN_SECURITY")

    items = {item["id"]: item for item in data["firm_items"]}
    trades = {t["trade_id"]: t for t in canonical["trades"]}
    for entry in data["entries"]:
        item = items[entry["entry_id"]]
        g.add_node(entry["date"], entry["entry_id"], node_type="CashMovement",
                   properties={"date": entry["date"], "recorded_at": entry["recorded_at"],
                               "amount": item["amount"],
                               "expected_date": item["expected_date"].isoformat(),
                               "entry_type": entry["entry_type"],
                               "reference": entry["reference"] or "",
                               "description": entry["description"],
                               "source": entry["source"]})
        g.add_edge(entry["date"], entry["entry_id"], account_id, layer="ON_ACCOUNT")
        if entry["portfolio_id"]:
            g.add_edge(entry["date"], entry["portfolio_id"], entry["entry_id"],
                       layer="HAS_MOVEMENT")
        if entry["trade_id"]:
            settles = trades[entry["trade_id"]]["settlement_date"]
            g.add_edge(settles, entry["trade_id"], entry["entry_id"], layer="SETTLED_BY")
        if entry["ticker"]:
            g.add_edge(entry["date"], entry["entry_id"], entry["ticker"], layer="DIVIDEND_ON")


def _add_bank(g: Graph, data: dict) -> None:
    header = data["header"]
    statement_id = header["statement_id"]
    g.add_node(header["period_end"], statement_id, node_type="BankStatement",
               properties={"period_start": header["period_start"].isoformat(),
                           "period_end": header["period_end"].isoformat(),
                           "opening_balance": header["opening_balance"],
                           "closing_balance": header["closing_balance"]})
    g.add_edge(header["period_end"], statement_id, header["account_id"], layer="FOR_ACCOUNT")
    for line in data["lines"]:
        g.add_node(line["date"], line["line_id"], node_type="BankEntry",
                   properties={"date": line["date"].isoformat(),
                               "line_number": line["line_number"],
                               "amount": line["amount"],
                               "entry_type": line["entry_type"] or "",
                               "reference": line["reference"] or "",
                               "description": line["description"]})
        g.add_edge(line["date"], statement_id, line["line_id"], layer="CONTAINS")


def _add_decisions(g: Graph, decisions: list[dict], run_at: datetime, run_id: str) -> None:
    for d in decisions:
        g.add_edge(run_at, d["bank_id"], d["firm_id"], layer="MATCHED_TO",
                   properties={"verdict": d["verdict"], "rule": d["rule"], "run_id": run_id,
                               "differences": json.dumps(d["differences"], default=_to_text),
                               "evidence": json.dumps(d["evidence"], default=_to_text)})


def finding_node_id(run_id: str, finding_id: str) -> str:
    """Findings are named per run, so a re-run's findings never merge with the first run's."""
    return f"{run_id}:{finding_id}"


def _add_findings(g: Graph, findings: list[dict], run: dict) -> None:
    for f in findings:
        at = datetime.fromisoformat(f["proposed_at"])
        node_id = finding_node_id(run["run_id"], f["finding_id"])
        g.add_node(at, node_id, node_type="Finding",
                   properties={"finding_id": f["finding_id"], "rule": f["rule"],
                               "category": f["category"], "type": f["type"],
                               "adjusts": f["adjusts"], "adjustment": Decimal(f["adjustment"]),
                               "status": f["status"], "proposed_by": f["proposed_by"],
                               "run_id": run["run_id"], "explanation": f["explanation"],
                               "evidence": json.dumps(f["evidence"])})
        g.add_edge(at, node_id, run["statement_id"], layer="FINDING_FOR")
        for firm_id in f["firm_ids"]:
            g.add_edge(at, node_id, firm_id, layer="EXPLAINS_MOVEMENT")
        for bank_id in f["bank_ids"]:
            g.add_edge(at, node_id, bank_id, layer="EXPLAINS_LINE")


# ---------------- snapshots ----------------

def describe(g: Graph) -> dict:
    """What a snapshot must keep: every node with its type and latest properties,
    every edge with its layers and latest properties. Used to check a snapshot."""
    return {
        "nodes": {n.name: (n.node_type, dict(n.properties)) for n in g.nodes},
        "edges": {(e.src.name, e.dst.name): (sorted(e.layer_names), dict(e.properties))
                  for e in g.edges},
    }


def save_snapshot(g: Graph, run_folder: Path, stage: str, at: datetime) -> Path:
    """Save the graph as Parquet in run_folder/graph/<time>_<stage>/, then load it
    back and check it describes the same graph. Never overwrites a snapshot."""
    folder = Path(run_folder) / "graph" / f"{at:%Y-%m-%dT%H-%M-%S}_{stage}"
    if folder.exists():
        raise FileExistsError(f"{folder} already exists; a snapshot is never overwritten")
    folder.parent.mkdir(parents=True, exist_ok=True)
    g.to_parquet(str(folder))
    if describe(load_snapshot(folder)) != describe(g):
        raise ValueError(f"{folder}: the snapshot does not load back the same graph")
    return folder


def load_snapshot(folder: Path) -> Graph:
    """Read a saved snapshot back into a graph."""
    return Graph.from_parquet(str(folder))


if __name__ == "__main__":
    import argparse
    from datetime import timezone

    parser = argparse.ArgumentParser(description="Build the graph for a saved run.")
    parser.add_argument("run_folder", type=Path, help="e.g. runs/ACC-KRW-CASH-01_2026-06/run-001")
    parser.add_argument("--snapshot", action="store_true", help="also save a checked snapshot")
    args = parser.parse_args()

    graph = build_graph(args.run_folder)
    print(f"{graph.count_nodes()} nodes, {graph.count_edges()} edges")
    for node_type in ("Client", "Portfolio", "Account", "AccountBalance", "Security", "Trade",
                      "CashMovement", "BankStatement", "BankEntry", "Finding"):
        count = sum(1 for n in graph.nodes if n.node_type == node_type)
        print(f"  {node_type:<15} {count}")
    if args.snapshot:
        folder = save_snapshot(graph, args.run_folder, "rules", datetime.now(timezone.utc))
        print(f"Snapshot saved to {folder}")
