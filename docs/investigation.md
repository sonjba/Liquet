# Investigation (Phase 2): the review log

Phase 1 ends with a saved run: decisions, findings and leftovers. Phase 2 is
everything after that: a rule's finding waiting for a person, the agent
proposing an explanation, a person approving or rejecting it. All of it is
recorded in one file in the run folder, `reviews.jsonl`, one event per line,
appended and never edited. The current state is worked out by replaying the
events in order (`review_log.py`).

Status: the log and its rules are built and tested with events written by
hand. The review command, the agent and the graph's review history come next
(see the build plan).

## The work list: what Phase 2 must settle

Computed from the run folder, never chosen by the agent:

- the items in Phase 1 findings (they still need a person's approval);
- the leftovers no rule could settle;
- bank lines matched with a difference that no finding explains;
- and, once a person disputes a rules match, that bank line and its entries.

For June that is seven items:

| Item | Why it is on the list | Break |
|---|---|---|
| CE-2026-06-0011 | R5 finding: payment in transit | B2 |
| CE-2026-06-0004, L5 | R2a finding: withholding tax | B3 |
| L11 | Fee group matched by R3 with +36.00 unexplained | B6 |
| L12 | Leftover bank line (custody fee) | B4 |
| L13 | Leftover bank line (credit interest) | B5 |
| CE-2026-06-0008 | Leftover firm entry (subscription) | B1 |

## Events

Every event has `event_id` (E0001, E0002, ...), `kind`, `by` and `at`.

| Kind | Who | Fields | Effect |
|---|---|---|---|
| `PROPOSED` | a rule, the agent or a person | `proposal_id`, `items`, `category`, `type`, `adjusts`, `adjustment`, `explanation`, `evidence` | Its items wait for a person |
| `APPROVED` | a person | `proposal_id` | Its items are settled |
| `REJECTED` | a person | `proposal_id`, `reason` | Its items are open again |
| `UNRESOLVED` | a person | `items`, `reason` | The items are closed with no explanation |
| `DISPUTED` | a person | `bank_id`, `reason` | A rules match is challenged: the bank line and its matched entries join the work list as OPEN |

- `by` is `agent`, a rule id (`R2a`, `R5`), or a person's short name (`sonja`).
- `at` is an ISO date-time, passed in by the caller. Events never go back in time.
- `adjustment` is money as text (`"-45.00"`), like every amount Liquet saves.
- The log starts with `open_review()`, which adds the Phase 1 findings as
  proposals by their rule, at the time the run made them.

Example:

```json
{"kind": "PROPOSED", "by": "R5", "at": "2026-07-02T09:30:00+00:00", "proposal_id": "R5:CE-2026-06-0011", "items": ["CE-2026-06-0011"], "category": "IN_TRANSITU", "type": "OUTSTANDING_PAYMENT", "adjusts": "bank", "adjustment": "-3717.00", "explanation": "Trade TR-26062901 settles on 2026-07-01, ...", "evidence": {...}, "event_id": "E0002"}
{"kind": "APPROVED", "by": "sonja", "at": "2026-07-02T10:15:00+00:00", "proposal_id": "R5:CE-2026-06-0011", "event_id": "E0003"}
```

## Rules

Checked when an event is appended, and again whenever the log is read, so a
log edited by hand that breaks a rule is caught. A refused event writes nothing.

1. Only a person approves, rejects or marks an item unresolved. Rules and the agent only propose.
2. An approval or rejection names one proposal that is still open.
3. A rejection, an "unresolved" and a dispute carry a reason.
4. A closed item (approved or unresolved) gets nothing more.
5. An item has at most one open proposal at a time: a person decides it before anyone proposes again.
6. The agent gets at most 2 proposals per item (`MAX_AGENT_ROUNDS`). After that, a person decides.
7. Every item belongs to this run's work list.
8. Events never go back in time.
9. Only a bank line the rules matched (CONGRUIT) can be disputed, once, and only while its items are open: a finding waiting on them is decided first, and a closed item stays closed.

## Disputing a rules match

The rules only match on exact evidence, but a person may still disagree, for
example with R4's name clue. A `DISPUTED` event names the bank line; the whole
match is challenged (for the fee group on L11, all five entries). Those items
then go through the same loop as any other: someone proposes, a person decides.

A proposal that disputed items *are* the same transaction (or are a different
pair) uses category `MATCH`, type `CONGRUIT`, adjustment `0.00`.

The rules' original decision stays in `decisions.json`, unchanged; the dispute
and what follows are in the log. The graph will show both.

## Item states

```
OPEN ──PROPOSED──► PROPOSED ──APPROVED──► APPROVED   (closed)
  ▲                    │
  └─────REJECTED───────┘
OPEN ──UNRESOLVED (a person)──► UNRESOLVED            (closed)

matched by the rules ──DISPUTED (a person)──► OPEN    (joins the work list)
```

## Decisions taken (easy to change later)

- **A person may approve their own proposal.** The state keeps who proposed
  and who decided, so it is visible. A team would usually require a second
  person (maker-checker); that would be one more rule.
- **Nobody can explain it** → a person records `UNRESOLVED` with a reason.
  The month's outcome is then `UNRESOLVED` (matching-rules.md, section 7).
- **People are named by a short name.** There is no list of allowed reviewers yet.
