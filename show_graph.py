"""Draw a run's graph as an interactive web page (open it in a browser).

    python show_graph.py runs/ACC-KRW-CASH-01_2026-06/run-001

Writes graph.html into the run folder. Drag nodes to move them, scroll to
zoom, hover a node to see its type and properties. Colours follow node types.

This is only a picture for people: it reads the graph, never changes it.
Needs pyvis (pip install pyvis); the page loads its drawing library from the
internet when opened.
"""

from __future__ import annotations

from pathlib import Path

from build_graph import build_graph


def short_label(node_id: str) -> str:
    """ACC-KRW-CASH-01:2026-06:L8 -> L8; .../run-001:R5:CE-2026-06-0011 -> R5 finding."""
    if "/run-" in node_id:                                   # a finding
        return node_id.split(":")[-2] + " finding"
    return node_id.split(":")[-1] if ":L" in node_id else node_id


def write_graph_page(run_folder: Path) -> Path:
    graph = build_graph(run_folder)
    net = graph.to_pyvis(colour_nodes_by_type=True, directed=True,
                         height="900px", width="100%", cdn_resources="remote")
    for node in net.nodes:
        raphtory_node = graph.node(node["id"])
        details = "\n".join(f"{key}: {value}" for key, value in raphtory_node.properties.items()
                            if key not in ("evidence",))
        node["label"] = short_label(node["id"])
        node["title"] = f"{raphtory_node.node_type}  {node['id']}\n{details}"
    page = Path(run_folder) / "graph.html"
    net.write_html(str(page), notebook=False)
    return page


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Draw a run's graph as a web page.")
    parser.add_argument("run_folder", type=Path)
    print(f"Open {write_graph_page(parser.parse_args().run_folder)} in a browser")