"""Read the firm's data and return it in Liquet's canonical shape.

Step 1: load one JSON file.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from read_statement import parse_money


def load_json(path: Path) -> list[dict]:
    """Read a JSON file that holds a list of records and return that list."""
    with open(path, "r", encoding="utf-8") as f:
        try:
            json_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"{path}: not valid JSON (line {e.lineno}): {e.msg}"
            ) from e

    if not isinstance(json_data, list):
        raise ValueError(
            f"{path}: expected a list of records, got {type(json_data).__name__}"
        )
    return json_data




