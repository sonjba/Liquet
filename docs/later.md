# Later: ideas agreed but parked

Written 18 October 2026, while polishing the June loop. Nothing here is built yet.

## Closing a month and carrying items forward

- `close_month.py`: a person marks a run **final** and writes `closing.json`:
  what is carried into next month and why. Refuses if a proposal is still waiting.
- A rejected rule finding leaves its items with no explanation, and the work list doesn't
  list them as open, so nothing can be proposed for them. close_month.py refuses for now.
- A month may close with an unexplained item if it is **carried with a reason**
  (real reconciliations carry outstanding items and escalate them as they age).
- Next month's run reads the previous **final** run's `closing.json`. It is Liquet's
  own format from a run folder, so it does not go through the door.
- Open question: book corrections (e.g. "book the custody fee -45") are assumed to be
  booked by the firm **dated in the old month**, so the next month's data stays clean.
  Check this against real practice.

## Timing rules

- **Direction decides the category.** Firm first, bank later = timing (IN_TRANSITU,
  adjust bank). Bank first, firm later = the books are incomplete (OMISSUM, adjust book).
- **R6, expected in transit (at close):** an open firm entry booked in the last few
  *working* days of the period, with no bank line yet, gets a PROPOSED finding with an
  `expected_by` date (its date + the payment method's travel time, in working days).
- **R0, cleared (next month):** a carried item matched by the same reference, or the same
  amount and client, dated on or after the original. By `expected_by`: on time. After it:
  cleared late, flagged. Different amount: cleared with a difference, a finding.
  Not cleared after `expected_by`: escalated.
- June's B1 (booked Friday 19 June, 7 working days before the end) must NOT be caught by
  R6: it is unusual, not normal timing. July's R0 should clear it as **late**.
  Its date cannot move: it makes the R4 decoy work.
- Book corrections as journal entries: the firm's corrections (dated in the month they
  belong to, entered later) as cash-book entries with their own types, each linked to the
  approved finding or proposal it carries out. Until then, July's fixture reflects June's
  corrections in its 30 June balance only. The answer keys' "journal" field is for this.

### Edge cases to cover

- Method: Faster Payments (minutes, can be held for fraud checks), CHAPS (same day,
  cut-off times), BACS (3-working-day cycle), SWIFT (days, charges deducted, other
  countries' holidays), cheques (clearing time, stale after about 6 months by common
  practice), trade settlement (T+2 now; UK T+1 planned, so a setting not a constant).
  Verify all exact figures before using them.
- For a firm-first item the bank line does not exist yet, so the method is often unknown:
  either the firm data carries `payment_method`, or R6 uses a cautious default.
- Calendar: month ending on a weekend (2026: 31 Jan, 28 Feb, 31 May, 31 Oct) or on a bank
  holiday (31 Aug 2026), Christmas and New Year, different UK nations' holidays,
  periods that do not end on the last day of a month.
- Dates on the files: value date vs booking date; time of day and cut-offs; firm entries
  back-dated after the data was extracted; "JUNE" in the text but dated 1 July.
- At clearing: in parts; with a deduction; late; never; then reversed; into another
  account; booked twice by the firm.

## A calendar connector

- One interface, e.g. `holidays(region, start, end)`, with connectors behind it
  (a file for tests and offline use, any holiday API a firm prefers).
- **Called at the door and saved in the run folder**, like the statement: holidays can
  change after the fact (the UK added 19 September 2022 at short notice), and a run must
  keep what it used. Tests never need the internet.
- Region comes from data (where the account is held), not from code.

## Months, history and the agent

- Full July fixture, bank **and** firm, with an answer key, designed to contain:
  June's B1 and B2 clearing on 1 July; normal July matches; the custody fee again
  (a precedent); and the Reid pair: bank +4,985.00 "SWIFT TRANSFER REID T" with no
  reference, firm +5,000.00 "Subscription Thomas Reid" (a 15.00 charge deducted).
- The bank half already exists in `tests/fixtures/2026-07/`.
- History graph built from all **final** runs, with CLEARED_BY edges between months.
- **Tier 2 agent:** runs only when tier 1 says NON_LIQUET or the checks refuse its answer.
  It gets the item, what tier 1 said, and a tool menu; a few rounds at most; a person
  always decides. First tools (one month): `open_items_for_party`, `near_amounts`,
  `amount_combinations`. Later (history): `find_precedents`.
- Before building the loop: check in the current API docs whether a forced answer format
  can be combined with tools, or whether to use a final `submit_answer` tool.
- `status.py`: where a month stands and what to do next.