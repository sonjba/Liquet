"""Follow paths such as "accounts[*].cash_balances[*].balance" through nested data.

This file knows nothing about the firm or about Liquet. It only follows the
paths it is given: firm_mapping.py holds the paths, and firm_connector.py
calls this file and then applies Liquet's own rules.

Writing a path
    accounts[*].cash_balances[*].balance
    = in the accounts data, for each account, for each item in its
      cash_balances list, take `balance`.

    name[*]   for each item in this list
    name?[*]  the same, but the list may be missing (then it has no items)
    a.b       field b inside the object in field a
    name?     this part may be missing: not there, or null
    None      instead of a path: the field is always None

    Everything without a ? must be there. A path starts with a dataset,
    such as accounts[*], and ends with a field name.

Records
    A block is one dict of  Liquet field: path. It makes one record per item
    of its deepest list. The record's own fields are the ones that go
    through that list. A field that stops at an earlier list is read from
    the parent item: a balance's account_id comes from its account.

When a part marked ? is missing
    - if every own field of the block goes through it, the item is skipped.
      In the trades block, a movement without trade? is not a trade.
    - otherwise only that field is None. In the cash book, a movement
      without trade? gets trade_id None.
    What comes after the ? is required again: a trade that is there but
    has no trade_ref is an error, not None.

Every record also gets `source`, the place it was found, for example
"accounts/ACC-1/cash_balances/0". Top-level items are named by their id
field (record_ids), nested ones by their position in the list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

UNKNOWN = "<unknown>"   # names a top-level item that has no id

# One step of a path: a name, then optionally ?, then optionally [*]
_STEP_PATTERN = re.compile(r"(\w+)(\?)?(\[\*\])?")


# ---------------- reading a path ----------------

@dataclass(frozen=True)
class Step:
    """One part of a path, such as `cash_movements[*]`, `trade?` or `trade_ref`."""
    name: str
    is_list: bool = False          # written name[*]
    may_be_missing: bool = False   # written name? (or name?[*] for a list)

    def __str__(self) -> str:
        return self.name + ("?" if self.may_be_missing else "") + ("[*]" if self.is_list else "")


def parse_path(path: str) -> list[Step]:
    """Split a path into its steps.

    "portfolios[*].cash_movements[*].trade?.trade_ref" gives four steps:
    portfolios[*], cash_movements[*], trade? and trade_ref.
    """
    steps = []
    for part in path.split("."):
        if part == "":
            raise ValueError(f"{path!r} has an empty step (two dots, or a dot at "
                             f"the start or end)")
        match = _STEP_PATTERN.fullmatch(part)
        if match is None:
            raise ValueError(f"{part!r} is not a valid step; "
                             f"write name, name?, name[*] or name?[*]")
        name, question_mark, list_mark = match.groups()
        steps.append(Step(name, is_list=bool(list_mark), may_be_missing=bool(question_mark)))
    return steps


def _text(steps: list[Step]) -> str:
    """Steps back to text, with their marks: "accounts[*].cash_balances[*]"."""
    return ".".join(str(step) for step in steps)


def _names(steps: list[Step]) -> str:
    """Just the names, as they appear in the data: "dividend.security"."""
    return ".".join(step.name for step in steps)


def _count_lists(steps: list[Step]) -> int:
    """How many lists ([*]) the steps go through."""
    return sum(1 for step in steps if step.is_list)


def _split_at_last_list(steps: list[Step]) -> tuple[list[Step], list[Step]]:
    """Split a path just after its last list.

    "accounts[*].cash_balances[*].balance"
        -> "accounts[*].cash_balances[*]"  (which item to read from)
           and "balance"                   (what to read inside it)
    """
    last = max(i for i, step in enumerate(steps) if step.is_list)
    return steps[: last + 1], steps[last + 1 :]


def _shared_start(a: list[Step], b: list[Step]) -> list[Step]:
    """The steps that a and b both start with.

    "p[*].m[*].trade?" and "p[*].m[*].dividend?" share "p[*].m[*]".
    """
    n = 0
    while n < len(a) and n < len(b) and a[n] == b[n]:
        n += 1
    return a[:n]


# ---------------- checking a mapping ----------------

@dataclass
class _Block:
    """One block of a mapping, checked and ready to use."""
    fields: dict[str, list[Step] | None]   # Liquet field -> its steps (None: always None)
    record_path: list[Step]                # where one record sits


def check_mapping(mapping: dict, record_ids: dict[str, str]) -> None:
    """Check every path in a mapping before any data is read.

    Stops at the first mistake and names its line, for example
    "trades.side: 'portfolios[*].cash_movements[*].trade?.side[*]' must end
    with a field name, not a list".
    """
    for name, blocks in mapping.items():
        for label, block in _labelled(blocks, name):
            _prepare(block, record_ids, label)


def _labelled(blocks, name: str):
    """Name each block for error messages: "trades", or "cash_book[0]",
    "cash_book[1]" when a collection has a list of blocks."""
    if isinstance(blocks, list):
        return [(f"{name}[{number}]", block) for number, block in enumerate(blocks)]
    return [(name, blocks)]


def _prepare(block, record_ids: dict[str, str], label: str) -> _Block:
    """Parse and check one block. `label` names it in error messages."""
    if not isinstance(block, dict):
        raise ValueError(f"{label}: expected a dict of Liquet field: path, "
                         f"got {type(block).__name__}")
    datasets = " or ".join(f"{dataset}[*]" for dataset in record_ids)

    fields = {}
    for liquet, path in block.items():
        where = f"{label}.{liquet}"
        if liquet == "source":
            raise ValueError(f"{where}: `source` is added automatically; remove this line")
        if path is None:
            fields[liquet] = None
            continue
        if not isinstance(path, str):
            raise ValueError(f"{where}: a path must be text or None, got {path!r}")
        try:
            steps = parse_path(path)
        except ValueError as error:
            raise ValueError(f"{where}: {error}") from None
        if not steps[0].is_list or steps[0].name not in record_ids:
            raise ValueError(f"{where}: {path!r} must start with {datasets}")
        if steps[-1].is_list:
            raise ValueError(f"{where}: {path!r} must end with a field name, not a list")
        fields[liquet] = steps

    paths = {liquet: steps for liquet, steps in fields.items() if steps is not None}
    if not paths:
        raise ValueError(f"{label}: needs at least one path, not only None")
    record_path = _record_path(paths, label)

    # A field must read from the record's own item or from one of its parents.
    for liquet, steps in paths.items():
        lists, _ = _split_at_last_list(steps)
        if lists != record_path[: len(lists)]:
            raise ValueError(
                f"{label}.{liquet}: {_text(steps)!r} does not lead to this "
                f"block's records ({_text(record_path)})")
    return _Block(fields, record_path)


def _record_path(paths: dict[str, list[Step]], label: str) -> list[Step]:
    """Where one record sits: the start that all of the record's own fields share.

    The own fields are the ones that go through the deepest list. In the
    trades block they all start with portfolios[*].cash_movements[*].trade?,
    so that is the record path, and a movement without a trade is skipped.
    In the cash book only trade_id goes through trade?, so the record path
    stops at the movement and trade_id is None when there is no trade.
    """
    deepest = max(_count_lists(steps) for steps in paths.values())
    own = [(liquet, steps) for liquet, steps in paths.items()
           if _count_lists(steps) == deepest]
    first_field, first_steps = own[0]

    # All own fields must reach the deepest list through the same lists.
    first_lists, _ = _split_at_last_list(first_steps)
    for liquet, steps in own[1:]:
        lists, _ = _split_at_last_list(steps)
        if lists != first_lists:
            raise ValueError(
                f"{label}: {first_field} and {liquet} come from different lists "
                f"({_text(first_lists)} and {_text(lists)}); one block makes "
                f"records from one list")

    # steps[:-1] leaves out the field name itself.
    shared = first_steps[:-1]
    for _, steps in own[1:]:
        shared = _shared_start(shared, steps[:-1])
    return shared


# ---------------- following the paths through the data ----------------

def extract(blocks, datasets: dict[str, list], record_ids: dict[str, str],
            name: str = "block") -> list[dict]:
    """Build records from the data by following the paths in `blocks`.

    blocks      one block, or a list of blocks when the records come from
                several places (the cash book: portfolios and accounts)
    datasets    the top-level data by name: {"accounts": [...], ...}
    record_ids  each dataset's id field, used to name records in `source`
    name        names the blocks in error messages
    """
    records = []
    for label, block in _labelled(blocks, name):
        prepared = _prepare(block, record_ids, label)
        for levels, source in _find_records(prepared.record_path, datasets, record_ids):
            record = {}
            for liquet, steps in prepared.fields.items():
                record[liquet] = None if steps is None else _read(liquet, steps, levels)
            record["source"] = source
            records.append(record)
    return records


def _find_records(record_path: list[Step], datasets: dict, record_ids: dict) -> list:
    """Follow the record path through the data. Return (levels, source) per record.

    `levels` has one (item, where) pair for each list on the way, outermost
    first. For a balance: [(its account, "accounts/ACC-1"),
                           (the balance, "accounts/ACC-1/cash_balances/0")].
    """
    top = record_path[0]   # always a dataset, such as accounts[*]
    if top.name not in datasets:
        raise ValueError(f"no data was given for {top.name!r}")
    found = []             # (levels, the object reached, its source)
    for item in _list_items(datasets[top.name], top.name):
        where = f"{top.name}/{_id_of(item, record_ids[top.name])}"
        found.append(([(item, where)], item, where))

    for step in record_path[1:]:
        next_found = []
        for levels, node, source in found:
            if step.is_list:
                value = node.get(step.name)
                if value is None and step.may_be_missing:
                    value = []     # a list marked ? may be missing: no items
                if value is None:
                    raise ValueError(f"{source}: missing {step.name!r}")
                for index, item in enumerate(_list_items(value, f"{source}/{step.name}")):
                    where = f"{source}/{step.name}/{index}"
                    next_found.append((levels + [(item, where)], item, where))
            else:
                value = node.get(step.name)
                if value is None and step.may_be_missing:
                    continue       # e.g. a movement without a trade is not a trade
                if value is None:
                    raise ValueError(f"{source}: missing {step.name!r}")
                if not isinstance(value, dict):
                    raise ValueError(f"{source}: {step.name!r} should be an object, "
                                     f"got {type(value).__name__}")
                next_found.append((levels, value, f"{source}/{step.name}"))
        found = next_found
    return [(levels, source) for levels, _, source in found]


def _list_items(value, where: str) -> list[dict]:
    """Check that `value` is a list of objects and return it."""
    if not isinstance(value, list):
        raise ValueError(f"{where}: should be a list, got {type(value).__name__}")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{where}/{index}: should be an object, "
                             f"got {type(item).__name__}")
    return value


def _id_of(item: dict, id_field: str) -> str:
    """The id that names a top-level item in `source`."""
    record_id = item.get(id_field)
    return UNKNOWN if record_id is None else str(record_id)


def _read(liquet: str, steps: list[Step], levels: list) -> object:
    """Read one field of one record.

    Start at the item of the field's last list (the record's own item, or a
    parent's), then follow the rest of the path inside it.
    """
    item, where = levels[_count_lists(steps) - 1]
    _, rest = _split_at_last_list(steps)
    value = item
    for n, step in enumerate(rest):
        if not isinstance(value, dict):
            raise ValueError(f"{where}: {_names(rest[:n])!r} should be an object, "
                             f"got {type(value).__name__} (for {liquet})")
        value = value.get(step.name)
        if value is None:
            if step.may_be_missing:
                return None
            raise ValueError(f"{where}: missing {_names(rest[: n + 1])!r} (for {liquet})")
    return value