"""Settings that change between places Liquet runs, read from the environment.

    LIQUET_RUNS_DIR   the folder that holds every run         (default: runs)
    LIQUET_MODEL      the Claude model investigate asks       (default: below)

ANTHROPIC_API_KEY is not read here: the Anthropic client reads it itself.

A command-line flag beats the environment, and the environment beats the default.
Business rules (the date tolerance, the tax rate, the reason codes) are not settings:
they stay in the code, where tests and review cover them.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_RUNS_DIR = Path("runs")
DEFAULT_MODEL = "claude-sonnet-5-5"


@dataclass(frozen=True)
class Settings:
    runs_dir: Path
    model: str


def load_settings(environ=None) -> Settings:
    """The settings from the environment, with .env loaded first.
    Pass `environ` (a dict) to read from it instead: tests do, so they never see .env."""
    if environ is None:
        load_dotenv()            # never overrides a variable that is already set
        environ = os.environ
    return Settings(
        runs_dir=Path(environ.get("LIQUET_RUNS_DIR") or DEFAULT_RUNS_DIR),
        model=environ.get("LIQUET_MODEL") or DEFAULT_MODEL,
    )