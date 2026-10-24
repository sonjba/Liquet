"""cli.py: one command, `liquet`, that hands each command to the module that owns it."""

import importlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from liquet.cli import COMMANDS, main
from liquet.pipeline.run_month import main as run_month

JUNE = Path(__file__).parent / "fixtures" / "2026-06"
SOURCES = {"header": JUNE / "statement_header.json", "lines": JUNE / "bank_statement.csv",
           "accounts": JUNE / "firm" / "accounts.json",
           "portfolios": JUNE / "firm" / "portfolios.json"}
RUN_AT = datetime(2026, 7, 2, 9, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("name", COMMANDS)
def test_every_command_has_a_module_with_a_cli(name):
    module = importlib.import_module(COMMANDS[name][0])
    assert callable(module.cli)


def test_no_command_shows_the_list_and_fails(capsys):
    assert main([]) == 2
    assert "investigate" in capsys.readouterr().out


def test_help_shows_the_list(capsys):
    assert main(["--help"]) == 0
    assert "decide" in capsys.readouterr().out


def test_an_unknown_command_fails_and_says_so(capsys):
    assert main(["reconcile"]) == 2
    assert "unknown command 'reconcile'" in capsys.readouterr().err


def test_a_command_gets_its_name_in_its_help(capsys):
    with pytest.raises(SystemExit) as stop:         # argparse stops after printing help
        main(["decide", "--help"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.startswith("usage: liquet decide")


def test_a_refused_decision_fails_and_says_why(tmp_path, capsys):
    # a finding that does not exist is refused; the exit code says so, so scripts can stop
    run = run_month(SOURCES, tmp_path / "runs", RUN_AT)["folder"]
    capsys.readouterr()                              # forget what the run printed
    code = main(["decide", str(run), "approve", "NO-SUCH-FINDING", "--by", "sonja",
                 "--code", "CONFIRMED"])
    assert code == 1
    assert capsys.readouterr().err.startswith("Not saved:")