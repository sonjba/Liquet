"""Run Liquet for one month: read both sides, check them, prepare them, match them."""

from __future__ import annotations

import argparse
from pathlib import Path

from bank_prepare import bank_to_item
from bank_reader import read_statement
from firm_checks import check_canonical
from firm_connector import FirmFileConnector
from firm_prepare import firm_to_item, parties_by_portfolio
from match import match


def main(args) -> dict:
    """Run every step in order. All data lives in `month`."""
    month = {}

    # 1. Bank: header + lines (read, checked, with ids)
    month["header"], month["lines"] = read_statement(args.header, args.lines)

    # 2. Firm: all collections, checked
    firm = FirmFileConnector(args.accounts, args.portfolios)
    check_canonical(firm.canonical, month["header"]["period_start"])
    month["firm"] = firm.canonical

    # 3. Firm entries for this account and month
    month["entries"] = firm.get_cash_entries(month["header"]["account_id"],
                                             month["header"]["period_start"],
                                             month["header"]["period_end"])

    # 4. Prepare both sides in the same shape for matching
    trades = {t["trade_id"]: t for t in month["firm"]["trades"]}
    month["bank_items"] = [bank_to_item(line) for line in month["lines"]]
    parties = parties_by_portfolio(month["firm"])
    month["firm_items"] = [firm_to_item(entry, trades, parties) for entry in month["entries"]]

    # 5. Match: pair bank items with firm items, rule by rule
    month["result"] = match(month["bank_items"], month["firm_items"],
                            period_end=month["header"]["period_end"])

    return month


def show(month: dict) -> None:
    """Print both sides and the matching result."""
    header = month["header"]
    print(f"Statement {header['statement_id']}: {header['period_start']} to {header['period_end']}")

    for title, items in (("Bank items", month["bank_items"]), ("Firm items", month["firm_items"])):
        print(f"\n{title}: {len(items)}")
        for item in items:
            short_id = item["id"].split(":")[-1]          # "L3" or "CE-2026-06-0002"
            print(f"  {short_id:<16} {item['expected_date']}  {item['amount']:>10}  "
                  f"{item['reference'] or '-':<16} {item['entry_type'] or '-':<17} {item['description']}")

    result = month["result"]
    print(f"\nDecisions: {len(result['decisions'])}")
    for d in result["decisions"]:
        diff = "".join(f"  diff {x['difference']}" for x in d["differences"])
        if "group_difference" in d["evidence"]:
            diff += f"  group diff {d['evidence']['group_difference']}"
        print(f"  {d['bank_id'].split(':')[-1]:<4} <-> {d['firm_id']}  "
              f"{d['rule']}  {d['verdict']}  lag {d['evidence']['lag_days']}d{diff}")
    print(f"\nFindings: {len(result['findings'])}")
    for f in result["findings"]:
        print(f"  {f['finding_id']:<22} {f['category']} / {f['type']}  "
              f"adjust {f['adjusts']} {f['adjustment']}  {f['status']}")

    print(f"\nUnmatched bank: {[i['id'].split(':')[-1] for i in result['unmatched_bank']]}")
    print(f"Unmatched firm: {[i['id'] for i in result['unmatched_firm']]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile one month.")
    parser.add_argument("--header", type=Path, required=True, help="bank statement header (JSON)")
    parser.add_argument("--lines", type=Path, required=True, help="bank statement lines (CSV)")
    parser.add_argument("--accounts", type=Path, required=True, help="firm accounts (JSON)")
    parser.add_argument("--portfolios", type=Path, required=True, help="firm portfolios (JSON)")
    args = parser.parse_args()

    month = main(args)
    show(month)