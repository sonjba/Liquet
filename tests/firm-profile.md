# Liquet — firm profile (synthetic)

All names below are invented. Any resemblance to real firms, people or securities is coincidental.

## The firm

**Kestrel Row Wealth Ltd** (KRW): a small UK wealth manager. It manages investment portfolios for private clients.

## The custodian and the account

- **Custodian:** Northgate Custody Bank (NCB), which holds the clients' cash and investments.
- **Account reconciled in v1:** `ACC-KRW-CASH-01`, the pooled client cash account, in GBP.
- **Each month,** KRW compares its own records (from its portfolio management system) with NCB's cash statement.

## Clients

| Client ID | Name | Typical activity |
|---|---|---|
| CL-001 | Amelia Hart | Regular subscriptions (adds money) |
| CL-002 | Daniel Okoro | Occasional large subscriptions |
| CL-003 | Priya Nair | Tops up by bank transfer, often with an unclear reference |
| CL-004 | Thomas Reid | Regular withdrawals (takes money out) |
| CL-005 | Hart Family Trust | Long-term holder, rarely moves cash |

## Securities traded

| Ticker | Name | Type | Approx. price (£) | Dividends |
|---|---|---|---|---|
| ALBN | Albion Utilities plc | UK share | 12.10–12.40 | Paid in full |
| SEVN | Severn Pharma plc | UK share | 24.80 | Paid in full |
| THIX | Thames Index Fund | Fund | 8.25 | Reinvested |
| ATIT | Atlantic Income Trust | Overseas fund | — | Paid net of 15% withholding tax |

## Operating rules (simplified for the synthetic data)

- **Settlement:** trades settle two business days after the trade date (T+2). The firm books a trade on the trade date; the cash moves on the settlement date.
- **Trading costs:** about £12–15 per trade, included in the settled amount.
- **Management fee:** charged monthly and transferred to KRW's fee account on the last business day.
- **Custody fee:** NCB charges £45 per month. KRW often records it late.
- **Interest:** NCB pays credit interest on the last day of the month.
- **Dividends:** KRW's system expects the gross amount; for overseas funds NCB pays net of withholding tax.
- **References:** subscriptions and withdrawals use `CL-xxx-SUB/WD-mmdd`; trades use `TR-yymmddnn`.

## What happened in June 2026

The June statement (`bank_statement.csv`) contains 12 lines: opening balance **250,000.00**, closing balance **285,378.57**.

Things that will matter when we build KRW's own records:

- **A trade on 29 June** (BUY ALBN, `TR-26062901`) settles on 1 July, so it's in KRW's records but **not** on the June statement: a timing difference (IN_TRANSITU).
- **The ATIT dividend** arrives net (1,275.00), but KRW expects the gross 1,500.00: an amount difference with an explanation.
- **Priya Nair's top-up** has the reference `PN TOPUP`, not her client code: the agent must work out who it belongs to.
- **The custody fee and the interest** are on the statement but not yet in KRW's records: omissions (OMISSUM).
