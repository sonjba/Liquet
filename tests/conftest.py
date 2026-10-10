"""Shared test set-up. pytest finds this file on its own.

- the --update-expected option (see test_firm_connector.py, golden file)
- the firm's June files, read once per test file
"""

from pathlib import Path

import pytest

from firm_connector import load_json

JUNE_FIRM = Path(__file__).parent / "fixtures" / "2026-06" / "firm"


def pytest_addoption(parser):
    parser.addoption(
        "--update-expected", action="store_true",
        help="rewrite the expected output files from the current code; "
             "read the change with git diff before committing it")


@pytest.fixture(scope="module")
def june_accounts():
    """The firm's June accounts. Shared by the tests in a file: don't change it."""
    return load_json(JUNE_FIRM / "accounts.json")


@pytest.fixture(scope="module")
def june_portfolios():
    """The firm's June portfolios. Shared by the tests in a file: don't change it."""
    return load_json(JUNE_FIRM / "portfolios.json")