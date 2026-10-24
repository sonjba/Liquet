"""Draw a saved graph snapshot as an interactive web page (open it in a browser).

    python -m liquet.graph.show_graph runs/ACC-KRW-CASH-01_2026-06/run-006/graph/2026-10-16T08-12-05_rules
Writes the page next to the snapshot, with the same name plus .html, so the
"before" and "after" pictures sit side by side and neither replaces the other:

    graph/2026-10-16T08-12-05_rules       graph/2026-10-16T08-12-05_rules.html
    graph/2026-10-16T08-20-41_review      graph/2026-10-16T08-20-41_review.html

Drag nodes to move them, scroll to zoom, hover a node to see its type and
properties. Colours follow node types. The page carries its own drawing code,
so it opens without the internet. It only reads the snapshot, never changes it.
Needs pyvis (pip install pyvis).
"""

from __future__ import annotations

from pathlib import Path
import sys

from liquet.graph.build_graph import load_snapshot


def short_label(node_id: str, node_type: str, properties: dict) -> str:
    """A short name for the picture, e.g. L8, R5 finding, D2 REJECTED, sonja."""
    if node_type == "Finding":
        return f"{properties.get('finding_id', node_id).split(':')[0]} finding"
    if node_type == "Decision":
        return f"{node_id.split(':')[-1]} {properties.get('kind', '')}"
    if node_type == "Actor":
        return node_id.replace(":", " ")                   # person sonja, rule R5
    return node_id.split(":")[-1]                          # L8, CE-2026-06-0007, PF-CL-005


def write_graph_page(snapshot_folder: Path) -> Path:
    snapshot_folder = Path(snapshot_folder)
    page = snapshot_folder.with_name(snapshot_folder.name + ".html")
    if page.exists():
        raise FileExistsError(f"{page} already exists; a picture is never overwritten")
    graph = load_snapshot(snapshot_folder)
    net = graph.to_pyvis(colour_nodes_by_type=True, directed=True,
                         height="900px", width="100%", cdn_resources="in_line")
    for node in net.nodes:
        raphtory_node = graph.node(node["id"])
        properties = dict(raphtory_node.properties)
        details = "\n".join(f"{key}: {value}" for key, value in properties.items()
                            if key not in ("evidence",))
        node["label"] = short_label(node["id"], raphtory_node.node_type, properties)
        node["title"] = f"{raphtory_node.node_type}  {node['id']}\n{details}"
    # pyvis's write_html uses the computer's default encoding (cp1252 on Windows),
    # which cannot hold every character in the page, so we save it as UTF-8 ourselves.
    page.write_text(net.generate_html(notebook=False), encoding="utf-8")
    return page


def cli(argv=None, prog=None):
    """The command line: `liquet ...` and `python -m ...` both come here."""
    import argparse

    parser = argparse.ArgumentParser(prog=prog, description="Draw a saved graph snapshot as a web page.")
    parser.add_argument("snapshot_folder", type=Path, help="a folder inside the run's graph/")
    print(f"Open {write_graph_page(parser.parse_args(argv).snapshot_folder)} in a browser")


if __name__ == "__main__":
    sys.exit(cli())