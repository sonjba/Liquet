# Liquet - file formats (v1)

The files Liquet receives from outside the firm: the bank statement. Plus the answer key used to score Liquet on synthetic data.

The firm's own records are not files. They live in the firm's database, described in `firm-database.md`, and reach Liquet through a connector (`canonical-format.md`).

One month = one folder:

```
<YYYY-MM>/
├── bank_statement.csv        ← the bank's lines for the month
├── statement_header.json     ← the statement's header: account, period, balances
├── firm/                     ← (synthetic data only) contents of the simulated firm database
│   ├── portfolios.json
│   └── accounts.json
└── answer_key.json           ← (synthetic data only) the correct result
```

## General rules

- **Encoding:** UTF-8; a byte order mark from Excel is accepted. **Dates:** ISO 8601, `YYYY-MM-DD`. **Currency:** GBP only in v1.
- **Amounts:** text with exactly two decimals (`1250.00`), never negative in `paid_in` / `paid_out`. A balance may be negative. In code, always `Decimal`, never `float`.
- **Empty values:** an empty cell, never `0`, `N/A` or `null`.
- **IDs:** banks don't always give each line an ID, so the reader creates a stable one from the line's contents and position. The same file always produces the same IDs.

## `bank_statement.csv`

Shaped like a typical bank export.

| Column | Example | Notes |
|---|---|---|
| `date` | `2026-06-18` | Date the bank booked it |
| `description` | `FASTER PAYMENT NAIR P` | The bank's own text, often abbreviated |
| `reference` | `PN TOPUP` | Often empty or unhelpful |
| `paid_in` | `5000.00` | Empty if money went out |
| `paid_out` | | Empty if money came in |
| `balance` | `264348.10` | Running balance after this line |

## `statement_header.json`

```json
{
  "account_id": "ACC-KRW-CASH-01",
  "custodian": "Northgate Custody Bank",
  "currency": "GBP",
  "period_start": "2026-06-01",
  "period_end": "2026-06-30",
  "opening_balance": "250000.00",
  "closing_balance": "285378.57"
}
```

Money is written as quoted text, so it's never read as a float.

## `answer_key.json` (synthetic data only)

The correct result for the month. Only tests and the scoring script read it. The engine and the agent never do.

```json
{
  "month": "2026-06",
  "account_id": "ACC-KRW-CASH-01",
  "balances": {
    "book_opening": "250000.00", "book_closing": "286683.20",
    "bank_opening": "250000.00", "bank_closing": "285378.57",
    "adjusted_bank": "286661.57", "adjusted_book": "286661.57",
    "true_cash_balance": "286661.57"
  },
  "matches": [
    {"bank_line": 8, "entries": ["CE-2026-06-0007"], "verdict": "CONGRUIT",
     "how": "...", "decoy": "CE-2026-06-0008"}
  ],
  "breaks": [
    {"id": "B4", "category": "OMISSUM", "type": "BANK_FEE",
     "entries": [], "bank_lines": [12], "amount": "45.00",
     "adjust_side": "book", "adjustment": "-45.00",
     "explanation": "...", "journal": "Dr Custody fees 45.00 / Cr Cash 45.00"}
  ]
}
```

| Part | Contents |
|---|---|
| `balances` | Both sides' opening and closing balances, both adjusted balances, and the true cash balance they agree on |
| `matches` | Each bank line and the firm entries it matches. **One bank line can match several entries**, which is why this is JSON, not CSV. Optional: `difference`, `decoy`, `break` |
| `breaks` | Each planted difference: category, type, the records involved, the adjustment and which side it applies to, the explanation and the journal (`null` for timing differences) |

Bank lines are identified by their line number in `bank_statement.csv` (header = line 1).

**Break types (v1):**
- `IN_TRANSITU` (timing): `DEPOSIT_IN_TRANSIT`, `OUTSTANDING_PAYMENT`
- `OMISSUM` (omissions): `MISSING_RECEIPT`, `INTEREST`, `BANK_FEE`, `WITHHOLDING_TAX`, `BOUNCED_PAYMENT`
- `ERRATUM` (errors): `BOOK_ERROR`, `BANK_ERROR`, `DUPLICATE`

## Decisions

1. **No signed amounts in the bank file.** Separate paid-in and paid-out columns avoid the "is minus money in or out?" mistake. The reader converts them to one signed amount: positive = money into the account.
2. **One account, one currency, one month per folder.** Multiple accounts and currencies come later.
3. **The answer key is kept apart from everything Liquet reads,** so its results can be scored honestly.