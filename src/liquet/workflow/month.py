"""The month, step by step: who acts at each step, the command, and the file that shows it is done.

    1. run          rules    liquet run            run.json
    2. investigate  LLM      liquet investigate    investigations.jsonl
    3. propose      person   liquet propose        proposals.jsonl   (only if a person has an explanation)
    4. decide       person   liquet decide         reviews.jsonl
    5. close        person   liquet close          closing.json

Each step leaves its file in the run folder, so the folder itself says how far the
month has got. People act between the steps, sometimes days apart: that is why the
month is a list of steps here, not one function that calls them.

    liquet status RUN       which steps are done, what waits for a person, what comes next

What each step adds to the graph is in docs/graph_map.yaml. Planned: a tier-2 agent
that investigates what one call to Claude could not explain (docs/later.md).
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from liquet.pipeline.carry import BROUGHT_FORWARD
from liquet.review.close_month import CLOSING, waiting_for_a_person
from liquet.review.decide import REVIEWS
from liquet.review.investigate import INVESTIGATIONS, already_proposed
from liquet.review.propose import PROPOSALS, load_proposals
from liquet.review.work_list import open_items
from liquet.store.run_store import RUN_FILE, load_run


@dataclass(frozen=True)
class Step:
    name: str
    actor: str        # who acts: rules, LLM or person
    command: str
    file: str         # the file in the run folder this step writes


STEPS = (
    Step("run", "rules", "liquet run", RUN_FILE),
    Step("investigate", "LLM", "liquet investigate RUN", INVESTIGATIONS),
    Step("propose", "person", "liquet propose RUN ITEM_ID ...", PROPOSALS),
    Step("decide", "person", "liquet decide RUN approve|reject FINDING --by NAME --code CODE", REVIEWS),
    Step("close", "person", "liquet close RUN --by NAME --reason TEXT", CLOSING),
)
STEP = {step.name: step for step in STEPS}


def status(run_folder) -> dict:
    """Where one run stands: which steps are done, what waits for a person, and what comes next."""
    run_folder = Path(run_folder)
    run = load_run(run_folder)                      # stops if the run did not finish
    done = {step.name: (run_folder / step.file).exists() for step in STEPS}
    # proposals.jsonl also holds Claude's proposals: "propose" is done only if a person proposed
    done["propose"] = any(p["proposer"] == "person" for p in load_proposals(run_folder))
    waiting = waiting_for_a_person(run_folder)
    proposed = already_proposed(run_folder)
    unexplained = [item["item_id"] for item in open_items(run_folder)
                   if item["item_id"] not in proposed]

    if done["close"]:
        next_step = None                            # final: next month starts with liquet run
    elif unexplained and not done["investigate"]:
        next_step = "investigate"
    elif waiting:
        next_step = "decide"
    else:
        next_step = "close"                         # still-unexplained items are carried, with a reason

    brought = run_folder / BROUGHT_FORWARD
    brought_forward = json.loads(brought.read_text(encoding="utf-8")) if brought.exists() else None
    return {"run_id": run["run"]["run_id"], "done": done, "waiting": waiting,
            "unexplained": unexplained, "next": next_step,
            "brought_forward_from": brought_forward["run_id"] if brought_forward else None}


def show(state: dict) -> None:
    print(state["run_id"])
    if state["brought_forward_from"]:
        print(f"  brought forward from {state['brought_forward_from']}")
    for number, step in enumerate(STEPS, start=1):
        if step.name == "decide" and state["waiting"]:
            note = f"waiting for a person: {', '.join(state['waiting'])}"
        else:
            note = "done" if state["done"][step.name] else "-"
        print(f"  {number}. {step.name:<12} {step.actor:<7} {note}")
    if state["unexplained"]:
        print(f"  open, no explanation yet: {', '.join(state['unexplained'])}")
    if state["next"]:
        print(f"Next: {STEP[state['next']].command}")
    else:
        print("Closed. Next month starts with: liquet run")


def cli(argv=None, prog=None):
    """The command line: `liquet ...` and `python -m ...` both come here."""
    parser = argparse.ArgumentParser(prog=prog, description="Where a run stands, and what comes next.")
    parser.add_argument("run_folder", type=Path)
    show(status(parser.parse_args(argv).run_folder))


if __name__ == "__main__":
    sys.exit(cli())
