# Liquet - matching rules (v1 design)

**Status: design, not built.** Nothing here is implemented yet. The thresholds (such as the date tolerance) are starting choices to revisit once there is code to test them against. Bank line numbers follow `answer_key.json`: the header is line 1, so the first transaction is line 2.

This document answers one question: given a bank statement and the firm's cash book for one month, how does Liquet decide what matches, and what does it report about everything that doesn't?

---

## 1. Two questions, not one

A bank line and a cash-book entry can be compared in two separate ways:

1. **Identity: are these the same transaction?**
2. **Agreement: do their details agree?** (amount, date, reference)

Keeping these apart is what makes the report make sense. A pair can be the same transaction and still disagree. The ATIT dividend is the clearest case: the bank line and the firm's entry are plainly the same dividend, but the bank paid £1,275.00 and the firm expected £1,500.00.

So:

- The **verdict** on a `MATCHED_TO` edge answers question 1.
- The edge's **differences** list answers question 2.
- A difference is not a failed match.

## 2. When a `MATCHED_TO` edge exists, and when it doesn't

| Situation | What Liquet writes |
|---|---|
| A pair, same transaction, everything agrees | `MATCHED_TO`, verdict `CONGRUIT`, differences empty |
| A pair, same transaction, something differs | `MATCHED_TO`, verdict `CONGRUIT`, differences listed. Plus a **Finding** explaining the difference. |
| A candidate pair that was considered and ruled out, with evidence | `MATCHED_TO`, verdict `DISCREPAT`, evidence says why. This keeps the reasoning. |
| A candidate exists but the evidence isn't enough to decide | `MATCHED_TO`, verdict `NON LIQUET`. A person decides. |
| **No candidate at all** | **No edge.** A **Finding** is attached to the unmatched record instead. |

"No match was found" is not the same as "the records are different". An item with no counterpart gets no edge and a finding. `DISCREPAT` is only written when there was a candidate and evidence against it.

### Why a Finding is a node, not an edge

The same rule as in the article: if you need to say something about a thing, make it a node. A finding has a status (proposed, approved, rejected), an adjustment, a journal and an approver. It can also concern several records at once, for example five fee entries and one bank line. An edge can't hold that.

A Finding links to the records it concerns with `EXPLAINS_MOVEMENT` and `EXPLAINS_LINE`, and to the month with `FINDING_FOR`.

## 3. What gets compared

| Field | Bank side | Firm side | Notes |
|---|---|---|---|
| Account | statement's account | movement's account | Always filtered first. Only items on the same account are candidates. |
| Amount | signed `amount` | signed `amount` | Positive = money in. Difference = **bank minus firm**. |
| Date | bank `date` | **expected date** (see below) | Within a tolerance of 1 calendar day to start. |
| Reference | `reference` | `reference` | Equal, or the bank's is empty or in a different style. |
| Text clue | `description` | client name, ticker | The weakest evidence. Used only to choose between candidates. |

**Expected date.** For most movements this is the movement's `date`. For a trade settlement it is the trade's **settlement date**, not the trade date, found by following `SETTLED_BY`. The firm records the cash movement on the trade date; the bank books it on the settlement date. Comparing bank dates with trade dates would make every settlement look late.

## 4. The rules, in order

Strictest first. A rule either concludes with written evidence or leaves the item for the next rule. Every conclusion records the rule's id.

**R1 - Exact.** References equal, amounts equal, bank date within tolerance of the expected date. Result: `CONGRUIT`, no differences. If the date differs by a day, the lag goes into the evidence.

**R2 - Same reference, amount differs.** References equal, exactly one counterpart, amounts differ. Result: `CONGRUIT`, with the amount difference listed. Then one exact check:

- **R2a - Withholding tax.** If the entry is a dividend, the security is overseas, and the difference is exactly 15% of the firm's amount, write a Finding: `OMISSUM / WITHHOLDING_TAX`. This is plain arithmetic with nothing to judge.

**R3 - One bank line, several entries.** Several entries share a reference with one bank line (`FEE-2026-06`). Add up the entries and compare with the bank amount. Result: one `CONGRUIT` edge per entry, all to the same bank line, with the total difference recorded in the evidence.

**R4 - No reference match: find candidates.** Take unmatched entries with the same amount and a date within tolerance.

- Exactly one candidate: `CONGRUIT`.
- Several candidates: use the text clue (does the bank's description name one candidate's client?). If exactly one fits, `CONGRUIT` with that one, and write `DISCREPAT` edges to the others with the reason.
- Several candidates and the clue doesn't settle it: `NON LIQUET`.

**R5 - Settlement after the period.** An unmatched trade-settlement entry whose settlement date is after the statement's end date, with no bank line. Result: Finding `IN_TRANSITU / OUTSTANDING_PAYMENT`. This is fully determined by the dates.

**Everything else goes to the agent.** Whatever is still unexplained after R1-R5 is the agent's job. It uses controlled, read-only tools and cannot change any record. See section 7.

## 5. Your June data, line by line

| Bank line | Entry | Rule | Result |
|---|---|---|---|
| 2 SUBSCRIPTION CL-001 | CE-0001 | R1 | CONGRUIT |
| 3 SETTLEMENT BUY 400 ALBN | CE-0002 | R1, expected date = trade's settlement date (3 June) | CONGRUIT |
| 4 SETTLEMENT SELL 250 SEVN | CE-0003 | R1, settlement date 5 June | CONGRUIT |
| 5 DIVIDEND ATIT | CE-0004 | R2, then R2a | CONGRUIT, difference **-225.00** (bank minus firm). Finding B3: withholding tax. |
| 6 WITHDRAWAL CL-004 | CE-0005 | R1, bank one day after the firm's date | CONGRUIT |
| 7 SETTLEMENT BUY 1000 THIX | CE-0006 | R1, settlement date 15 June | CONGRUIT |
| 8 FASTER PAYMENT NAIR P | CE-0007 | R4: two £5,000 candidates (CE-0007, CE-0008); "NAIR P" names Priya Nair | CONGRUIT with CE-0007. **DISCREPAT** edge to CE-0008. |
| 9 SUBSCRIPTION CL-002 | CE-0009 | R1 | CONGRUIT |
| 10 SETTLEMENT SELL 600 ALBN | CE-0010 | R1, settlement date 26 June | CONGRUIT |
| 11 TRANSFER FEE-2026-06 | CE-0012 to CE-0016 | R3 | CONGRUIT for all five, difference **-36.00** in total. Needs an explanation (agent). |
| 12 CUSTODY FEE | none | none | No edge. Agent proposes: omission, bank fee (B4). |
| 13 CREDIT INTEREST | none | none | No edge. Agent proposes: omission, interest (B5). |
| none | CE-0011 (buy 300 ALBN) | R5: settles 1 July, after 30 June | Finding B2: in transit. |
| none | CE-0008 (Hart Family Trust) | none (ruled out for line 8) | No edge to a bank line. Agent proposes: deposit in transit (B1). |

**What the rules solve alone:** all ten matched bank lines (lines 2 to 11), plus B2 and B3. **What goes to the agent:** B1, B4, B5 and B6. That is four of the six planted breaks, plus the decoy as a check on the rules.

## 6. What the agent does with the leftovers

The agent calls tested tools. It doesn't fetch data by itself and doesn't write queries. Tools the leftovers need:

- **Find a transposition in a group.** For a group with a difference (the fee transfer), try swapping adjacent digits in each entry. If exactly one swap makes the group total equal the bank amount, that entry is the likely error. For June: 473.50 becomes 437.50, and no other entry works. Swapping adjacent digits always changes a number by a multiple of 9, and 36.00 is divisible by 9. That is why this check is worth running first.
- **Classify an unmatched bank line.** Look at its description ("CUSTODY FEE", "CREDIT INTEREST") and check no firm entry has that amount. Propose `OMISSUM` with a type.
- **Propose a timing difference.** An unmatched firm entry with no bank line: propose `IN_TRANSITU`.
- **Residual check.** After all other findings, how much of the gap is still unexplained, and does it equal the unmatched items? In June, the opening gap between book and bank is £1,304.63. Findings B2 to B6 explain -£3,695.37. The remaining £5,000.00 is exactly CE-0008.

**One caution about B1.** From the June data alone, the residual check shows that CE-0008 is *consistent* with a deposit in transit, but it doesn't prove it. The answer key states "arrives at the bank 1 July", which only the July statement can confirm. So the finding is **PROPOSED**, with the evidence "residual equals this entry exactly; confirm on the next statement". A person approves it. This is also why the cross-month check (does the in-transit item clear next month?) matters.

Each finding must carry evidence the person can check. An agent proposal with no evidence is not a finding.

## 7. What the report looks like

```
Reconciliation: ACC-KRW-CASH-01, June 2026

Bank closing balance (statement)                285,378.57
  + B1  Deposit in transit, CE-2026-06-0008      +5,000.00   proposed, confirm on July statement
  - B2  Payment in transit, CE-2026-06-0011      -3,717.00   TR-26062901 settles 1 July
Adjusted bank balance                           286,661.57

Book closing balance (cash book)                286,683.20
  - B3  Withholding tax on ATIT dividend           -225.00   1,500.00 gross, 1,275.00 paid (15%)
  - B4  Custody fee not recorded                    -45.00   bank line 12
  + B5  Interest not recorded                      +212.37   bank line 13
  + B6  Fee recorded 473.50, should be 437.50       +36.00   CE-2026-06-0012, digits swapped
Adjusted book balance                           286,661.57

Unreconciled amount                                   0.00
```

Below it, the person sees every bank line and every firm entry with its status: matched, matched with differences, or a finding. Anything `NON LIQUET` is listed separately as needing a decision.

**Monthly outcome**

| Outcome | When |
|---|---|
| `MATCHED` | Every item matched, no findings |
| `EXPLAINED DIFFERENCE` | Every difference has an approved finding, and the unreconciled amount is 0.00 (**LIQUET**) |
| `UNRESOLVED` | Any item is `NON LIQUET`, or the unreconciled amount isn't zero |

June is `EXPLAINED DIFFERENCE` once the person has approved the findings.

## 8. Checks after matching (stop the run if any fails)

1. Each `CashMovement` has at most one `CONGRUIT` edge.
2. Every bank line and every movement is accounted for: it is in a `CONGRUIT` edge, or it has a Finding.
3. The adjustments in the findings reproduce both adjusted balances, and the two are equal. If not, the outcome is `UNRESOLVED`.

## 9. What each rule asks of the graph

| Question | Graph path |
|---|---|
| Which entries are on this account in this window? | `CashMovement` -`ON_ACCOUNT`-> `Account`, filtered by date |
| When does this trade's cash really move? | `Trade` -`SETTLED_BY`-> `CashMovement`, read the settlement date |
| Whose movement is this (for a text clue)? | `Portfolio` -`HAS_MOVEMENT`-> `CashMovement`, `Client` -`OWNS_PORTFOLIO`-> `Portfolio` |
| Is this dividend security overseas? | `CashMovement` -`DIVIDEND_ON`-> `Security`, read `domicile` |
| Which statement is this line in? | `BankStatement` -`CONTAINS`-> `BankEntry` |

## 10. Open decisions

1. **Where the line sits between rules and agent.** This draft keeps rules to matching and to explanations that are exact arithmetic or exact dates. Everything that needs judgment goes to the agent. The alternative is to let rules classify "CUSTODY FEE" and "INTEREST" lines too. That would leave the agent almost nothing to do on June, which is a poor test of the agent. Keeping it as drawn gives the agent four real breaks and the decoy to work on.
2. **Date tolerance.** 1 calendar day fits the June data. Business days is a later refinement.
3. **How strict the text clue is.** "NAIR P" works because the surname and initial fit exactly one client. How to handle abbreviations that fit two clients is open. The safe default is `NON LIQUET`.
4. **The answer key's sign convention.** `answer_key.json` records the dividend difference as `225.00` and the fee difference as `-36.00`. With "bank minus firm" the dividend should be `-225.00`. Fix this before using the answer key to evaluate anything.
5. **Next month (designed, not built).** Findings still open at month end are carried forward. Each run first loads them and looks for their bank line on the new statement. If it's there, a `CLEARED_BY` edge links the finding to that line, which also confirms an in-transit explanation the earlier month could only propose. If not, the finding stays open and is flagged as overdue after one more month. A pattern that repeats can become a rule only if it describes how things normally work (a buy agreed at month end settles next month). A mistake that repeats (the same wrong fee every month) is flagged to be fixed at the source, never turned into a rule. Testing this needs a July fixture.
6. **Harder months.** June is easy for the rules. To test whether the graph helps the agent, a later month needs breaks the rules can't settle.