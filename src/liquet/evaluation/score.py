import json
import sys
from decimal import Decimal
from pathlib import Path

from liquet.review.decide import load_reviews
from liquet.review.propose import load_proposals
from liquet.store.run_store import load_run


def explanations(run):
    """Every explanation in the run that no person rejected: the rules' findings, then proposals."""
    reviews = {review["finding_id"]: review["kind"] for review in load_reviews(run)}
    found = [{"by": f"rule:{finding['rule']}", "ids": finding["bank_ids"] + finding["firm_ids"],
              "category": finding["category"], "type": finding["type"],
              "adjusts": finding["adjusts"], "adjustment": finding["adjustment"]}
             for finding in load_run(run)["findings"]
             if reviews.get(finding["finding_id"]) != "REJECTED"]
    for proposal in load_proposals(run):
        if reviews.get(proposal["proposal_id"]) != "REJECTED":
            found.append({"by": f"{proposal['proposer']}:{proposal['proposed_by']}",
                          "ids": proposal["item_ids"],
                          "category": proposal["category"], "type": proposal["type"],
                          "adjusts": proposal["adjusts"], "adjustment": proposal["adjustment"]})
    return found

def score(run, answer_key):
    """Each break in the answer key: RIGHT, WRONG, or OPEN, and who explained it."""
    statement = f"{answer_key['account_id']}:{answer_key['month']}"
    results = []
    for brk in answer_key["breaks"]:
        ids = set(brk["entries"]) | {f"{statement}:L{n}" for n in brk["bank_lines"]}
        mine = [e for e in explanations(run) if ids & set(e["ids"])]
        if not mine:
            results.append({"break": brk["id"], "verdict": "OPEN", "by": None})
            continue
        e = mine[-1]                                   # the latest explanation counts
        right = (e["category"], e["type"], e["adjusts"], Decimal(e["adjustment"])) == (
            brk["category"], brk["type"], brk["adjust_side"], Decimal(brk["adjustment"]))
        results.append({"break": brk["id"], "verdict": "RIGHT" if right else "WRONG",
                        "by": e["by"]})
    return results


if __name__ == "__main__":
    answer_key = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    results = score(Path(sys.argv[1]), answer_key)
    for r in results:
        print(f"  {r['break']}  {r['verdict']:<6} {r['by'] or ''}")
    for verdict in ("RIGHT", "WRONG", "OPEN"):
        print(f"{verdict}: {sum(r['verdict'] == verdict for r in results)}", end="   ")
    print()