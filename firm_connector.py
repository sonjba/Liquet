"""Read the firm's data and return it in Liquet's canonical shape.

Done so far: accounts, recorded balances, portfolios, clients, the cash book,
trades and securities.
Where each field comes from is written in firm_mapping.py as a path, for
example "accounts[*].cash_balances[*].balance". This file follows those
paths and applies Liquet's own rules; it never names a firm field itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from firm_mapping import FIRM_DIRECTION_CODES, FIRM_MAPPING, FIRM_RECORD_IDS

UNKNOWN = "<unknown>"


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


# ---------------- following the paths in firm_mapping.py ----------------

def _parse(path: str) -> tuple[list[tuple[str, bool, bool]], bool]:
    """Split a path into steps of (name, is_list, skip_if_missing).

    'a[*].b?.c?' -> ([('a', True, False), ('b', False, True), ('c', False, False)],
                     optional=True)
    A '?' at the very end makes the field optional; a '?' on an earlier step
    means "only items that have this object; skip the others"."""
    optional = path.endswith("?")
    if optional:
        path = path[:-1]
    steps = []
    for part in path.split("."):
        if part.endswith("[*]"):
            steps.append((part[:-3], True, False))
        elif part.endswith("?"):
            steps.append((part[:-1], False, True))
        else:
            steps.append((part, False, False))
    return steps, optional


def _depth(steps) -> int:
    """How many lists ([*]) a path goes through."""
    return sum(1 for _, is_list, _ in steps if is_list)


def _record_steps(parsed: dict) -> list[tuple[str, bool]]:
    """Where one record sits: the part shared by the fields that go deepest."""
    deepest = max(_depth(steps) for steps, _ in parsed.values())
    parents = [steps[:-1] for steps, _ in parsed.values() if _depth(steps) == deepest]
    common = parents[0]
    for other in parents[1:]:
        n = 0
        while n < min(len(common), len(other)) and common[n] == other[n]:
            n += 1
        common = common[:n]
    return common


def _walk(datasets: dict, steps: list, levels: list, node, source: str):
    """Yield (items at each list level, source) for every record under `steps`."""
    if not steps:
        yield levels, source
        return
    name, is_list, skip_if_missing = steps[0]
    if is_list:
        children = datasets[name] if not levels else node.get(name, [])
        if not isinstance(children, list):
            raise ValueError(f"{source}: {name!r} should be a list")
        for index, child in enumerate(children):
            if not levels:   # a top-level record: named by its id
                record_id = child.get(FIRM_RECORD_IDS[name]) if isinstance(child, dict) else None
                child_source = f"{name}/{UNKNOWN if record_id is None else record_id}"
            else:            # a nested record: named by its position
                child_source = f"{source}/{name}/{index}"
            yield from _walk(datasets, steps[1:], levels + [child], child, child_source)
    else:
        child = node.get(name) if isinstance(node, dict) else None
        if not isinstance(child, dict):
            if skip_if_missing:
                return   # e.g. a movement with no trade: not a trade record
            raise ValueError(f"{source}: missing or invalid {name!r}")
        yield from _walk(datasets, steps[1:], levels, child, f"{source}/{name}")


def _read_field(levels: list, steps: list, optional: bool, source: str):
    """Read one field: start at the item of its deepest list, then follow the rest."""
    depth = _depth(steps)
    value = levels[depth - 1]
    rest = steps[[i for i, (_, is_list, _) in enumerate(steps) if is_list][depth - 1] + 1:]
    for name, *_ in rest:
        if not isinstance(value, dict) or name not in value:
            if optional:
                return None
            raise ValueError(f"{source}: missing field {'.'.join(n for n, *_ in rest)!r}")
        value = value[name]
    return value


def _extract(datasets: dict, block: dict) -> list[dict]:
    """Build one Liquet record per item of the deepest list in `block`."""
    parsed = {liquet: _parse(path) for liquet, path in block.items() if path is not None}
    constants = [liquet for liquet, path in block.items() if path is None]
    records = []
    for levels, source in _walk(datasets, _record_steps(parsed), [], None, ""):
        record = {liquet: _read_field(levels, steps, optional, source)
                  for liquet, (steps, optional) in parsed.items()}
        record |= {liquet: None for liquet in constants}
        record["source"] = source
        records.append(record)
    return records


# ---------------- one function per canonical collection ----------------

def to_accounts(raw_accounts: list[dict]) -> list[dict]:
    """Convert the firm's accounts to Liquet's canonical `accounts`."""
    return _extract({"accounts": raw_accounts}, FIRM_MAPPING["accounts"])


def to_account_balances(raw_accounts: list[dict]) -> list[dict]:
    """Convert the balances inside the firm's accounts to Liquet's canonical
    `account_balances`: one record per balance, with its account's id."""
    return _extract({"accounts": raw_accounts}, FIRM_MAPPING["account_balances"])


def to_portfolios(raw_portfolios: list[dict]) -> list[dict]:
    """Convert the firm's portfolios to Liquet's canonical `portfolios`."""
    return _extract({"portfolios": raw_portfolios}, FIRM_MAPPING["portfolios"])


def to_trades(raw_portfolios: list[dict]) -> list[dict]:
    """Convert the trades inside the firm's trade-settlement movements to
    Liquet's canonical `trades`: one record per movement that has a trade."""
    return _extract({"portfolios": raw_portfolios}, FIRM_MAPPING["trades"])


def _one_per_id(records: list[dict], id_field: str, what: str) -> list[dict]:
    """Keep one record per id when the firm copies the same thing into several
    places (a client in each portfolio, a security in each trade).

    Copies must agree; if two differ, stop and name both places. Liquet never
    silently picks one (canonical check 7). The first copy's `source` is kept."""
    by_id = {}
    for record in records:
        details = {k: v for k, v in record.items() if k != "source"}
        record_id = record[id_field]
        if record_id in by_id:
            first = by_id[record_id]
            if {k: v for k, v in first.items() if k != "source"} != details:
                raise ValueError(
                    f"{what} {record_id}: details differ between {first['source']} "
                    f"and {record['source']}")
            continue   # same thing, already recorded
        by_id[record_id] = record
    return list(by_id.values())


def to_clients(raw_portfolios: list[dict]) -> list[dict]:
    """Convert the clients embedded in the firm's portfolios to Liquet's
    canonical `clients`: one record per client, even when a client owns
    several portfolios."""
    clients = _extract({"portfolios": raw_portfolios}, FIRM_MAPPING["clients"])
    return _one_per_id(clients, "client_id", "Client")


def to_securities(raw_portfolios: list[dict]) -> list[dict]:
    """Convert the securities copied inside the firm's trades and dividends to
    Liquet's canonical `securities`: one record per ticker."""
    copies = []
    for block in FIRM_MAPPING["securities"]:
        copies += _extract({"portfolios": raw_portfolios}, block)
    return _one_per_id(copies, "ticker", "Security")


def to_cash_book(raw_accounts: list[dict], raw_portfolios: list[dict]) -> list[dict]:
    """Convert the firm's cash movements to Liquet's canonical `cash_book`:
    client movements from each portfolio, then account movements (fees,
    interest) that belong to no client. The firm's direction code decides
    whether the amount is a debit (money in) or a credit (money out)."""
    datasets = {"accounts": raw_accounts, "portfolios": raw_portfolios}
    entries = []
    for block in FIRM_MAPPING["cash_book"]:
        for entry in _extract(datasets, block):
            direction = entry.pop("direction")
            amount = entry.pop("amount")
            column = FIRM_DIRECTION_CODES.get(direction)
            if column is None:
                raise ValueError(
                    f"{entry['source']}: direction must be "
                    f"{' or '.join(FIRM_DIRECTION_CODES)}, got {direction!r}")
            entry["debit"] = amount if column == "debit" else None
            entry["credit"] = amount if column == "credit" else None
            entries.append(entry)
    return entries


if __name__ == "__main__":
    raw_accounts = load_json(Path("tests/fixtures/2026-06/firm/accounts.json"))
    raw_portfolios = load_json(Path("tests/fixtures/2026-06/firm/portfolios.json"))
    print(to_accounts(raw_accounts))
    print(to_account_balances(raw_accounts))
    print(to_portfolios(raw_portfolios))
    print(to_clients(raw_portfolios))
    cash_book = to_cash_book(raw_accounts, raw_portfolios)
    print(len(cash_book))   # expect 17
    print(cash_book[1])     # CE-2026-06-0002: trade_id TR-26060101, credit 4852.40
    trades = to_trades(raw_portfolios)
    print(len(trades))      # expect 5
    print(to_securities(raw_portfolios))   # expect ALBN, THIX, SEVN, ATIT