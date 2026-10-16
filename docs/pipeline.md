# Liquet's pipeline

One rule shapes the whole pipeline: **data is turned into Liquet's format once,
at the door, and stored. After that, nothing reads anything except Liquet's
format.** A new bank or a new firm system changes the door and nothing else.

## The stages, in order

`run_month.py` runs them in this order. Each stage uses only what the stages
before it produced (a straight-line DAG: the bank and firm sides enter side by
side, then everything runs on one path).

```
 ┌─ THE DOOR (integration: the only code that knows outside formats) ──────────┐
 │  bank header + CSV ─► bank_reader + bank_mapping ───► Liquet bank statement  │
 │  firm files / DB   ─► firm_connector + firm_mapping ─► Liquet canonical data │
 └──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
          runs/<account>_<YYYY-MM>/run-NNN/received/  + liquet_format/
                                   │  everything below reads liquet_format/ only
                                   ▼
          prepare ─► match ─► check ─► decisions / findings / leftovers, run.json
                                   │
                                   ▼
          build_graph (later: agent, review, report)
```

| # | Stage | Code | Reads | Writes / produces |
|---|---|---|---|---|
| 1 | receive | `run_store.fingerprints` | the arriving files | a SHA-256 fingerprint of each |
| 2 | ingest (**the door**) | `run_month.ingest`: `bank_reader`, `bank_mapping`, `firm_connector`, `firm_mapping`, `path_mapper`, `firm_checks` | the arriving files | the bank statement (header and lines, each line with `entry_type` and `reference`) and the firm's canonical collections and month's cash entries, all checked |
| 3 | store | `run_month.store`: `run_store.save_received`, `save_liquet_format`, `load_liquet_format` | stage 2's data | `received/` (exact copies, checked against stage 1's fingerprints) and `liquet_format/` (Liquet format). The data is then read back, and the run stops if it doesn't match what was saved. |
| 4 | prepare | `bank_prepare.bank_items`, `firm_prepare.firm_items` | the data read back from `liquet_format/` | matching items, the same 10 keys on both sides |
| 5 | match | `match.match` | items | decisions, findings, leftovers |
| 6 | check | `match_checks.check_match_result` | items + result | stops the run if anything is matched twice or lost |
| 7 | save | `run_store.save_results` | result | `decisions.json`, `findings.json`, `leftovers.json`, then `run.json` last |
| – | graph | `build_graph.build_graph` | `liquet_format/` + results only | the temporal graph and Parquet snapshots in `graph/` |

## A run folder

```
runs/ACC-KRW-CASH-01_2026-06/run-001/
  received/   header.json, lines.csv, accounts.json, portfolios.json   (as they arrived)
  liquet_format/  bank_statement.json, firm_canonical.json, firm_cash_entries.json   (Liquet format)
  decisions.json, findings.json, leftovers.json
  run.json    run_id, run_at, statement, received files + fingerprints, stages, counts
  graph/      <time>_<stage>/  Parquet snapshots
```

- `run.json` is written last. A run folder without it did not finish, but its
  `received/` and `liquet_format/` folders show how far it got.
- Nothing in a run folder is changed or overwritten. A month run again gets a
  new `run-NNN`.
- Money and dates are stored as text (`"-225.00"`, `"2026-06-30"`) and become
  `Decimal` and `date` again when read back.

## Why store before matching

- **What is stored is what was used.** Matching runs on the data read back from
  `liquet_format/`, so the stored data is exactly the input to matching, not a copy made
  afterwards.
- **History stays true.** The graph is rebuilt from `liquet_format/`, never from the
  original files or the current mappings. If a mapping changes next year, a
  June 2026 run still shows what Liquet saw in June 2026.
- **A failed run keeps its evidence.** If matching or a check stops the run,
  the received files and the Liquet data are already saved.

## Adding a new bank or firm

1. Write a reader and a mapping for its format. It must produce the same
   Liquet bank statement, or the same canonical collections.
2. Call it in `run_month.ingest`.
3. Nothing else changes. `tests/test_boundaries.py` fails if any module after
   the door imports door code, directly or through another module.

## What is not here (yet)

- No DAG engine. The order is simply the order of the calls in
  `run_month.main`, and `run.json` lists the stages that ran.
- `reviews.jsonl` (approvals, rejections and agent proposals) will be added to
  the run folder as an append-only event log, and the graph will be rebuilt
  from `liquet_format/`, the results and those events.
