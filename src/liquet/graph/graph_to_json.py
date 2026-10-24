"""A saved graph snapshot as a JSON file you can read.

    python -m liquet.graph.graph_to_json runs/.../graph/<time>_review

Writes <snapshot>.json next to the snapshot folder. Never overwrites one.
Nodes are grouped by type, edges by layer, so you can find
"every Decision" or "every DECIDES edge" in one place.
"""

import argparse
import json
from pathlib import Path
import sys

from liquet.graph.build_graph import load_snapshot


def graph_as_dict(graph) -> dict:
    nodes, edges = {}, {}
    for node in graph.nodes:
        nodes.setdefault(node.node_type, []).append(
            {"id": node.name, "properties": dict(node.properties)})
    for edge in graph.edges:
        for layer in sorted(edge.layer_names):
            edges.setdefault(layer, []).append(
                {"from": edge.src.name, "to": edge.dst.name, "properties": dict(edge.properties)})
    return {"counts": {"nodes": graph.count_nodes(), "edges": graph.count_edges(),
                       "by_node_type": {t: len(n) for t, n in nodes.items()},
                       "by_edge_layer": {layer: len(e) for layer, e in edges.items()}},
            "nodes": nodes, "edges": edges}


def write_graph_json(snapshot_folder: Path) -> Path:
    snapshot_folder = Path(snapshot_folder)
    page = snapshot_folder.with_name(snapshot_folder.name + ".json")
    if page.exists():
        raise FileExistsError(f"{page} already exists; it is never overwritten")
    content = {"snapshot": snapshot_folder.name, **graph_as_dict(load_snapshot(snapshot_folder))}
    # default=str: money stays exact text ("-225.00"), dates become ISO text
    page.write_text(json.dumps(content, indent=2, default=str), encoding="utf-8")
    return page


def cli(argv=None, prog=None):
    """The command line: `liquet ...` and `python -m ...` both come here."""
    parser = argparse.ArgumentParser(prog=prog, description="Write a saved graph snapshot as readable JSON.")
    parser.add_argument("snapshot_folder", type=Path, help="a folder inside the run's graph/")
    print(f"Written {write_graph_json(parser.parse_args(argv).snapshot_folder)}")


if __name__ == "__main__":
    sys.exit(cli())