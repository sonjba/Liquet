"""One command for all of Liquet: `liquet <command> ...`.

This file only chooses which module handles a command. Each module keeps its own
options in its cli() function, next to the code it runs, so `python -m liquet.review.decide`
still works the same as `liquet decide`.
"""

import importlib
import sys

# command: (module that handles it, what it does). The order is the order of a month.
COMMANDS = {
    "run":         ("liquet.pipeline.run_month",   "reconcile one month: read, match, save a run"),
    "report":      ("liquet.pipeline.report",      "read a saved run back"),
    "open-items":  ("liquet.review.work_list",     "list what the rules left open"),
    "facts":       ("liquet.review.facts",         "show the facts Claude gets for one open item"),
    "investigate": ("liquet.review.investigate",   "ask Claude to explain the open items"),
    "propose":     ("liquet.review.propose",       "a person proposes an explanation"),
    "decide":      ("liquet.review.decide",        "approve or reject a finding or a proposal"),
    "close":       ("liquet.review.close_month",   "mark a run final and carry what is left"),
    "graph":       ("liquet.graph.build_graph",    "build the graph for a run, and save a snapshot"),
    "graph-json":  ("liquet.graph.graph_to_json",  "write a snapshot as readable JSON"),
    "graph-page":  ("liquet.graph.show_graph",     "draw a snapshot as a web page"),
    "score":       ("liquet.evaluation.score",     "score a run against an answer key (the builder's check)"),
    "status":      ("liquet.workflow.month",       "where a run stands, and what comes next"),
}


def usage() -> str:
    """The list of commands, as `liquet` and `liquet --help` print it."""
    width = max(len(name) for name in COMMANDS)
    rows = "\n".join(f"  {name:<{width}}  {about}" for name, (_, about) in COMMANDS.items())
    return (f"usage: liquet <command> [options]\n\ncommands:\n{rows}\n\n"
            f"liquet <command> --help shows a command's options.")


def main(argv=None) -> int:
    """Run one command; return its exit code (0 = done, anything else = it failed)."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(usage())
        return 0 if argv else 2
    name, rest = argv[0], argv[1:]
    if name not in COMMANDS:
        print(f"liquet: unknown command {name!r}\n\n{usage()}", file=sys.stderr)
        return 2
    module = importlib.import_module(COMMANDS[name][0])   # only the module this command needs
    return module.cli(rest, prog=f"liquet {name}") or 0