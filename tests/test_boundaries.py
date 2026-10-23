"""Which parts of Liquet may use which: the rules, checked on the code itself.

Each folder under src/liquet/ is a part. A part may import from itself and from the
parts listed for it in ALLOWED, nothing else. The rules are about folders, not file
names, so they keep working when a file is renamed or a new file is added.

Two rules matter most:
- the door: only the pipeline reads outside formats. Everything after it sees
  Liquet's own format.
- evaluation: nothing imports it. The score is the builder's check, and the agent
  must never see the answer key.
"""

import ast
from pathlib import Path

import pytest

LIQUET = Path(__file__).parent.parent / "src" / "liquet"

ALLOWED = {
    "door":       set(),                                     # outside formats in, nothing else
    "canonical":  set(),                                     # checks on Liquet's format
    "store":      set(),                                     # the run folder
    "matching":   set(),                                     # prepare and match, R0-R5
    "review":     {"matching", "store"},                     # open items, Claude, decisions
    "graph":      {"matching", "review", "store"},           # the temporal graph
    "pipeline":   {"door", "canonical", "matching", "store"},  # runs a month: the only door user
    "evaluation": {"review", "store"},                       # the score: nobody imports it
}


def parts():
    """Every folder under src/liquet/ that holds code."""
    return sorted(p.name for p in LIQUET.iterdir() if p.is_dir() and list(p.rglob("*.py")))


def liquet_imports(source: str) -> set[str]:
    """The parts of Liquet a piece of source imports: liquet.review.decide -> review."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                raise ValueError("relative import: write it as liquet.<part>.<module>")
            names = [node.module or ""]
        else:
            continue
        found |= {name.split(".")[1] for name in names if name.startswith("liquet.")}
    return found


def test_every_part_has_a_rule():
    # A new folder must be given its rule here before it can be used.
    assert set(parts()) == set(ALLOWED)


@pytest.mark.parametrize("part", sorted(ALLOWED))
def test_a_part_imports_only_what_it_may(part):
    broken = {}
    for file in sorted((LIQUET / part).rglob("*.py")):
        extra = liquet_imports(file.read_text(encoding="utf-8")) - {part} - ALLOWED[part]
        if extra:
            broken[str(file.relative_to(LIQUET))] = sorted(extra)
    assert broken == {}


def test_only_the_pipeline_may_use_the_door():
    assert [part for part, may in ALLOWED.items() if "door" in may] == ["pipeline"]


def test_nothing_may_use_evaluation():
    assert [part for part, may in ALLOWED.items() if "evaluation" in may] == []


def test_the_check_would_catch_it():
    # review reaching into the door, and the agent reading the score: both must show up.
    source = ("from liquet.door.bank.bank_reader import read_lines\n"
              "import liquet.evaluation.score\n")
    assert liquet_imports(source) - {"review"} - ALLOWED["review"] == {"door", "evaluation"}