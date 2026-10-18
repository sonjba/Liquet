"""Only the door knows outside formats.

The door is the code that reads a bank's or a firm's own files and turns
them into Liquet's format. Everything after it must work from Liquet's
format alone, so a new bank or firm changes the door and nothing else.
These tests read each module's imports (and their imports, and so on) and
fail if a module after the door reaches into it.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

DOOR = {"bank_reader", "bank_mapping", "firm_connector", "firm_mapping", "path_mapper"}

AFTER_THE_DOOR = ["bank_prepare", "firm_prepare", "firm_checks", "match", "match_checks",
                  "run_store","investigate", "build_graph", "show_graph"]


def _local_imports(module: str) -> set[str]:
    """The Liquet modules this module imports directly."""
    tree = ast.parse((ROOT / f"{module}.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return {name for name in names if (ROOT / f"{name}.py").exists()}


def _all_imports(module: str) -> set[str]:
    """Everything the module imports from Liquet, directly or through others."""
    seen, todo = set(), [module]
    while todo:
        for name in _local_imports(todo.pop()) - seen:
            seen.add(name)
            todo.append(name)
    return seen


@pytest.mark.parametrize("module", AFTER_THE_DOOR)
def test_nothing_after_the_door_imports_the_door(module):
    assert _all_imports(module) & DOOR == set()


def test_the_check_would_catch_it():
    # run_month is the one place that calls the door, so it must show up here.
    assert {"bank_reader", "firm_connector"} <= _all_imports("run_month")
