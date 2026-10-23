"""Which code produced a result: the Liquet version and the git commit.

A run folder already keeps what came in (received/) and what came out. This adds
which code turned one into the other, so an auditor can trace a result back to
the exact code, and anyone can check it out and get the same result again.

If the code had changes that were not committed, the result cannot be traced to
a commit, and the record says so instead of pretending.
"""

import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

CODE_FOLDER = Path(__file__).parent    # ask git about where the code is, not where you stand


def _git(*args: str) -> str | None:
    """git's answer about CODE_FOLDER; None if git is missing or this is not a git checkout."""
    try:
        done = subprocess.run(["git", *args], cwd=CODE_FOLDER,
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def release_info() -> dict:
    """{"liquet_version", "git_commit", "uncommitted_changes"}; "unknown" / None when it cannot tell."""
    try:
        liquet_version = version("liquet")
    except PackageNotFoundError:
        liquet_version = "unknown"
    commit = _git("rev-parse", "HEAD")
    changes = _git("status", "--porcelain")
    return {
        "liquet_version": liquet_version,
        "git_commit": commit or "unknown",
        "uncommitted_changes": None if changes is None else changes != "",
    }