# Liquet — the firm's database (simulated, v1)

How Kestrel Row Wealth Ltd stores its own records. In development, a local ArangoDB plays this database, filled from generated JSON files.

This is what the **connector reads**. What the connector **returns** is described in `canonical-format.md`. The connector's job is to turn one into the other.

The design follows the typical document-database style: **one rich document per main thing, with lists inside that grow as events arrive**. It is designed from general wealth-management concepts and does not copy any real firm's schema.

## Collections

| Collection | One document per | Lists that grow |
|---|---|---|
| `portfolios` | Client | `cash_movements`: every cash movement for that client |
| `accounts` | Custodian account | `account_movements`: movements that belong to no client (custody fee, interest) |

There are no separate `clients`, `trades` or `securities` collections. That information lives **inside** the documents above, as it typically does in an embedded design.

## General rules

- **Dates:** text, `"YYYY-MM-DD"`.
- **Money:** text with two decimals, in quotes, never negative. Direction is a separate field: `"IN"` or `"OUT"`.
- **The firm uses its own field names** (`value_date`, `narrative`, `our_ref`…). The connector maps them to the canonical names.

## `portfolios`

One document per client. The client's details sit at the top; every cash movement for the client is in `cash_movements`. A trade movement embeds the trade, and the trade embeds a copy of the security's details. A dividend movement embeds a copy of the security too.

```json
{
  "_key": "PF-CL-001",
  "portfolio_id": "PF-CL-001",
  "custody_account": "ACC-KRW-CASH-01",
  "client": {
    "client_id": "CL-001",
    "full_name": "Amelia Hart",
    "type": "individual"
  },
  "cash_movements": [
    {
      "movement_id": "CE-2026-06-0001",
      "value_date": "2026-06-01",
      "entered_on": "2026-06-01",
      "kind": "SUBSCRIPTION",
      "narrative": "Subscription Amelia Hart",
      "our_ref": "CL-001-SUB-0601",
      "direction": "IN",
      "amount": "25000.00"
    },
    {
      "movement_id": "CE-2026-06-0002",
      "value_date": "2026-06-01",
      "entered_on": "2026-06-01",
      "kind": "TRADE_SETTLEMENT",
      "narrative": "Buy 400 ALBN",
      "our_ref": "TR-26060101",
      "direction": "OUT",
      "amount": "4852.40",
      "trade": {
        "trade_ref": "TR-26060101",
        "side": "BUY",
        "trade_date": "2026-06-01",
        "settle_date": "2026-06-03",
        "qty": 400,
        "unit_price": "12.10",
        "fees": "12.40",
        "consideration": "4852.40",
        "security": {
          "ticker": "ALBN",
          "name": "Albion Utilities plc",
          "type": "share",
          "domicile": "uk"
        }
      }
    }
  ]
}
```

### Movement fields

| Field | Example | Notes |
|---|---|---|
| `movement_id` | `"CE-2026-06-0001"` | Unique across the firm |
| `value_date` | `"2026-06-01"` | When the movement happened. For trades: the trade date. |
| `entered_on` | `"2026-06-01"` | When the firm recorded it |
| `kind` | `"SUBSCRIPTION"` | `SUBSCRIPTION`, `WITHDRAWAL`, `TRADE_SETTLEMENT`, `DIVIDEND`, `MANAGEMENT_FEE`, `CUSTODY_FEE`, `INTEREST` |
| `narrative` | `"Buy 400 ALBN"` | Free text |
| `our_ref` | `"TR-26060101"` | The firm's reference (formats as in `canonical-format.md`) |
| `direction` | `"OUT"` | `"IN"` or `"OUT"` |
| `amount` | `"4852.40"` | Never negative |
| `trade` | `{...}` | Only on `TRADE_SETTLEMENT` |
| `dividend` | `{"security": {...}}` | Only on `DIVIDEND` |

## `accounts`

One document per custodian account, with the movements that belong to no client.

```json
{
  "_key": "ACC-KRW-CASH-01",
  "account_id": "ACC-KRW-CASH-01",
  "name": "Client cash account",
  "custodian": "Northgate Custody Bank",
  "currency": "GBP",
  "account_movements": [
    {
      "movement_id": "CE-2026-05-0031",
      "value_date": "2026-05-31",
      "entered_on": "2026-06-02",
      "kind": "CUSTODY_FEE",
      "narrative": "Custody fee May",
      "our_ref": "NCB-FEE-0526",
      "direction": "OUT",
      "amount": "45.00"
    }
  ]
}
```

## How the connector maps this to the canonical format

| Canonical | Comes from |
|---|---|
| **`accounts`** | |
| `account_id`, `custodian`, `currency` | The same fields in `accounts` |
| `account_name` | `accounts.name` |
| **`clients`** | |
| `client_id` | `portfolios.client.client_id` |
| `name` | `portfolios.client.full_name` |
| `client_type` | `portfolios.client.type` |
| **`portfolios`** | |
| `portfolio_id` | `portfolios.portfolio_id` |
| `client_id` | `portfolios.client.client_id` |
| `account_id` | `portfolios.custody_account` |
| **`securities`** (one per ticker) | |
| `ticker`, `name`, `domicile` | Every copy in `trade.security` and `dividend.security`. All copies must agree (canonical check 7). |
| `security_type` | `security.type` |
| **`trades`** | |
| `trade_id` | `trade.trade_ref` |
| `portfolio_id` | The parent portfolio's `portfolio_id` |
| `account_id` | The parent portfolio's `custody_account` |
| `ticker` | `trade.security.ticker` |
| `side`, `trade_date` | The same fields in `trade` |
| `settlement_date` | `trade.settle_date` |
| `quantity` / `price` / `costs` | `trade.qty` / `trade.unit_price` / `trade.fees` |
| `settlement_amount` | `trade.consideration` |
| **`cash_book`** | |
| `entry_id` | `movement_id` |
| `account_id` | The parent portfolio's `custody_account`, or the parent account's `account_id` |
| `date` / `recorded_at` | `value_date` / `entered_on` |
| `entry_type` / `description` / `reference` | `kind` / `narrative` / `our_ref` |
| `portfolio_id` | The parent portfolio's `portfolio_id`; `null` for account movements |
| `trade_id` | `trade.trade_ref`, if present |
| `ticker` | `dividend.security.ticker`, if present |
| `debit` / `credit` | `amount` goes to `debit` if `direction` is `IN`, to `credit` if `OUT` |
| `source` | Where it was found, e.g. `"portfolios/PF-CL-001/cash_movements/1"` |

## Simplifications in v1

- One custodian account; every portfolio uses it.
- Each trade belongs to one client's portfolio (no trades split across clients).
- Each dividend is paid to one client's portfolio.
- GBP only.

## Decisions to review

1. **The firm uses its own field names** (`value_date`, `narrative`, `our_ref`, `direction` + `amount`). That's realistic, and it gives the connector real mapping work.
2. **Client movements live in the client's portfolio; account movements in the account document.** To reconcile the pooled account, the connector gathers movements from every portfolio plus the account document. That's how a pooled account really works: the bank sees one account, and the firm's records are spread across its clients.
3. **Security details are copied into every trade and dividend.** Typical of embedded designs, and a realistic source of inconsistencies, which canonical check 7 catches.
4. **The management fee is recorded per client,** each with reference `FEE-YYYY-MM`, but the bank shows **one** transfer for the total. One bank line matches several cash-book entries, a realistic case for matching rules and the agent.
5. **Every portfolio movement carries its `portfolio_id`,** added by the connector from the parent document. Account movements have none. (Applied in `canonical-format.md`: cash entries and trades record their portfolio, and clients are reached through it.)