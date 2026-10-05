# Liquet - canonical format (v1)

This is the shape Liquet works with: the firm's records as **separate, flat documents with explicit IDs**. It doesn't matter how the firm stores its data. Liquet connects to the firm's database **read-only**, through a **connector**, and the connector returns everything in this shape. Version 1 connects to a document database (ArangoDB) whose documents are nested; a relational connector can be added later without changing anything else in Liquet.

How the simulated firm actually stores its data is described in `firm-database.md`.

Liquet's own results (verdicts, evidence, approvals) are never written to the firm's database. They are kept in Liquet's own store.

## Canonical collections

| Collection | One document per | Example ID |
|---|---|---|
| `accounts` | Account at the custodian | `ACC-KRW-CASH-01` |
| `clients` | Client | `CL-003` |
| `securities` | Security the firm trades | `ATIT` |
| `trades` | Buy or sell | `TR-26062901` |
| `cash_book` | Cash movement the firm recorded | `CE-2026-06-0007` |

Every canonical document also carries a `source` field saying exactly where in the firm's data it came from, for example `"portfolios/CL-003/cash_movements/4"`.

## General rules

- **Currency:** GBP only in v1.
- **Dates:** text, `"YYYY-MM-DD"`.
- **Money:** text with exactly two decimals, in quotes: `"4852.40"`, never a JSON number. JSON numbers are read as floats, which can quietly change amounts. Never negative. In code: `Decimal`.
- **Not applicable:** `null`. For example, `client_id` on a trade settlement.
- **IDs:** every document has an ID that is unique within its collection and never changes. It is also the document's `_key`.

## `accounts`

| Field | Example | Notes |
|---|---|---|
| `account_id` | `"ACC-KRW-CASH-01"` | |
| `account_name` | `"Client cash account"` | |
| `custodian` | `"Northgate Custody Bank"` | Must match the statement header |
| `currency` | `"GBP"` | |

## `clients`

| Field | Example | Notes |
|---|---|---|
| `client_id` | `"CL-003"` | |
| `name` | `"Priya Nair"` | |
| `client_type` | `"individual"` | `"individual"` or `"trust"` |

## `securities`

| Field | Example | Notes |
|---|---|---|
| `ticker` | `"ATIT"` | Used as the ID |
| `name` | `"Atlantic Income Trust"` | |
| `security_type` | `"fund"` | `"share"` or `"fund"` |
| `domicile` | `"overseas"` | `"uk"` or `"overseas"`. Overseas dividends may arrive net of tax. |

## `trades`

| Field | Example | Notes |
|---|---|---|
| `trade_id` | `"TR-26062901"` | |
| `account_id` | `"ACC-KRW-CASH-01"` | |
| `ticker` | `"ALBN"` | |
| `side` | `"BUY"` | `"BUY"` (cash goes out) or `"SELL"` (cash comes in) |
| `trade_date` | `"2026-06-29"` | When the trade was agreed |
| `settlement_date` | `"2026-07-01"` | When the cash moves (T+2) |
| `quantity` | `400` | Whole number (a JSON number is fine here; it isn't money) |
| `price` | `"12.10"` | Per unit |
| `costs` | `"12.40"` | Trading costs |
| `settlement_amount` | `"4852.40"` | BUY: quantity × price + costs. SELL: quantity × price − costs. |

## `cash_book`

Debit = money in, credit = money out, the accounting convention from the bank reconciliation method.

| Field | Example | Notes |
|---|---|---|
| `entry_id` | `"CE-2026-06-0007"` | |
| `account_id` | `"ACC-KRW-CASH-01"` | |
| `date` | `"2026-06-18"` | When the movement happened |
| `recorded_at` | `"2026-06-19"` | When the firm entered it. Lets us ask "what did we know, and when?" |
| `entry_type` | `"SUBSCRIPTION"` | `SUBSCRIPTION`, `WITHDRAWAL`, `TRADE_SETTLEMENT`, `DIVIDEND`, `MANAGEMENT_FEE`, `CUSTODY_FEE`, `INTEREST` |
| `description` | `"Top-up Priya Nair"` | Free text |
| `reference` | `"CL-003-SUB-0618"` | The firm's reference (formats below) |
| `client_id` | `"CL-003"` | For subscriptions and withdrawals, otherwise `null` |
| `trade_id` | `null` | For trade settlements, otherwise `null` |
| `ticker` | `null` | For dividends, otherwise `null` |
| `debit` | `"5000.00"` | Money in, otherwise `null` |
| `credit` | `null` | Money out, otherwise `null` |
| `source` | `"portfolios/CL-003/cash_movements/4"` | Where in the firm's data this entry came from |

One complete cash entry:

```json
{
  "_key": "CE-2026-06-0007",
  "entry_id": "CE-2026-06-0007",
  "account_id": "ACC-KRW-CASH-01",
  "date": "2026-06-18",
  "recorded_at": "2026-06-19",
  "entry_type": "SUBSCRIPTION",
  "description": "Top-up Priya Nair",
  "reference": "CL-003-SUB-0618",
  "client_id": "CL-003",
  "trade_id": null,
  "ticker": null,
  "debit": "5000.00",
  "credit": null,
  "source": "portfolios/CL-003/cash_movements/4"
}
```

### Reference formats

| Format | Meaning |
|---|---|
| `CL-xxx-SUB-mmdd` | Client subscription (money in) |
| `CL-xxx-WD-mmdd` | Client withdrawal (money out) |
| `TR-yymmddnn` | Trade settlement |
| `DIV-TICKER-mmdd` | Dividend |
| `FEE-YYYY-MM` | Monthly management fee transfer |

## Checks after retrieving (stop if any fails)

Liquet runs these on whatever a connector returns, before using the data:

1. **IDs are unique** within each collection.
2. **Every reference to another collection exists.** Each `account_id`, `client_id`, `trade_id` and `ticker` points to a real document.
3. **Trades add up.** `settlement_amount` matches quantity × price ± costs.
4. **Cash book entries:** exactly one of `debit` or `credit` is filled, and the right link field is filled for the `entry_type`. A `TRADE_SETTLEMENT` has a `trade_id`, a `DIVIDEND` has a `ticker`, and so on.
5. **Cash book matches its trade.** A trade settlement's amount equals its trade's `settlement_amount`.
6. **Money fields are text, not numbers.** A number in a money field is rejected.
7. **Repeated copies agree.** When the firm's data copies the same fact into several places (a security's name or domicile inside every trade, a client's name inside every movement), all copies must match. A mismatch is reported with every conflicting copy. Liquet never silently picks one.

## Separating nested data

When the firm stores data nested (one big document per client, with lists inside), the connector takes it apart into canonical documents. Three rules:

1. **Carry the parent's identity into each child.** A movement inside a client's portfolio doesn't mention the client; it just sits inside the document. The connector adds `client_id` (and anything else the parent knows) to each movement it takes out, so the link isn't lost.
2. **Check repeated copies; never silently pick one.** See check 7.
3. **Record where each document came from** in its `source` field, so any explanation can point back to the exact place in the firm's data.

## Connectors

Liquet asks for data through one set of functions, for example `get_cash_entries(account_id, start, end)`. Each connector implements the same functions and returns documents in the shape above:

| Connector | How it reads | When |
|---|---|---|
| **Document database** | AQL queries against the firm's ArangoDB, with a read-only user. Takes nested lists apart into canonical documents. | Version 1 |
| **Relational database** | SQL queries, with the results mapped to these fields | Later |

For testing: a file connector offers the same functions but reads the firm's data from JSON files instead of the database. Tests use it, so they run without a database.

Everything after the connector (checks, graph, matching and the agent) works the same whichever connector is used.

## Decisions to review

1. **Liquet reads the firm's database directly, read-only,** and keeps its own results separately. The firm's official record is never changed.
2. **Links in the canonical format are explicit fields** (`client_id`, `trade_id`, `ticker`). When the firm's data is nested, the connector adds them from the parent document. The hard linking is between the **bank** and the firm: bank lines carry only text, like `PN TOPUP`, and that's where matching rules and the agent do their work.
3. **Debit and credit in the cash book,** like the reconciliation method. The reader converts both sides to one signed amount: positive = money in.
4. **Money as quoted text, `null` for not applicable.** Exact amounts, and no confusion between "empty" and "zero".
5. **Dividends are recorded gross** (what the firm expects). The difference from a net payment at the bank is a real break to explain.
6. **The checks stop the run.** The fix your article recommends for production: never quietly work around bad source data.