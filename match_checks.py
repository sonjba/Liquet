"""Check the matching result before Liquet uses it (matching-rules.md, section 8).

Like firm_checks.py: each check returns a list of problems, and
check_match_result() stops the run if there are any, listing them all.

These checks guard the matching code itself. If a rule ever pairs one firm
entry twice, or loses or invents an item, the run stops here instead of
producing a report that quietly doesn't add up.
"""

from __future__ import annotations

from collections import Counter


class MatchCheckError(ValueError):
    """The matching result failed one or more checks. `problems` lists them."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} problem(s) in the matching result:\n  "
                         + "\n  ".join(problems))


def check_match_result(bank_items: list[dict], firm_items: list[dict], result: dict) -> None:
    """Run every check; raise MatchCheckError listing all problems found."""
    problems = (check_one_congruit_per_firm_item(result)
                + check_every_item_accounted_for(bank_items, result, "bank")
                + check_every_item_accounted_for(firm_items, result, "firm"))
    if problems:
        raise MatchCheckError(problems)


def check_one_congruit_per_firm_item(result: dict) -> list[str]:
    """Check 1: a firm entry is matched to at most one bank line."""
    counts = Counter(d["firm_id"] for d in result["decisions"] if d["verdict"] == "CONGRUIT")
    return [f"check 1, {firm_id}: matched (CONGRUIT) {n} times"
            for firm_id, n in counts.items() if n > 1]


def check_every_item_accounted_for(items: list[dict], result: dict, side: str) -> list[str]:
    """Check 2: every item ends up in exactly one place, and nothing appears
    from nowhere.

    Settled = in a CONGRUIT decision or named by a Finding.
    Left over = in the unmatched list, for the agent and the person.
    Each item must be one or the other, never both, never neither.
    """
    id_field = f"{side}_id"
    ids_field = f"{side}_ids"
    settled = ({d[id_field] for d in result["decisions"] if d["verdict"] == "CONGRUIT"}
               | {i for f in result["findings"] for i in f[ids_field]})
    left_over = [item["id"] for item in result[f"unmatched_{side}"]]
    known = {item["id"] for item in items}

    problems = []
    for item_id in sorted(known):
        if item_id in settled and item_id in left_over:
            problems.append(f"check 2, {side} {item_id}: settled and also left over")
        elif item_id not in settled and item_id not in left_over:
            problems.append(f"check 2, {side} {item_id}: lost (neither settled nor left over)")
    for item_id, n in Counter(left_over).items():
        if n > 1:
            problems.append(f"check 2, {side} {item_id}: left over {n} times")
    mentioned = settled | set(left_over) | {d[id_field] for d in result["decisions"]}
    for item_id in sorted(mentioned - known):
        problems.append(f"check 2, {side} {item_id}: not among the {side} items")
    return problems