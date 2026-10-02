# Liquet

**AI-assisted monthly bank reconciliation: rules match, an agent explains the rest, a person approves.**

*Liquet — Latin for "it is clear."*

---

## Project Description

### The problem

Every month, a business has to reconcile its own cash records against its bank statement.

Most transactions match automatically. The remaining differences have to be investigated and explained, which can be slow, repetitive, and difficult to trace.

### The constraint

The records come from different sources and in different formats.

A reconciliation result also needs to be explainable: an accountant or auditor should be able to see **what was decided, why it was decided, and what evidence supports it.**

### The approach

Liquet separates deterministic matching from investigation.

1. **Rules** match records where the evidence is clear.
2. A **graph layer** connects records to their matches, explanations, related transactions, and history across months.
3. An **AI agent** investigates unresolved differences using a small set of controlled tools.
4. A **person approves** the proposed explanation or correction.
5. Every decision and its evidence is recorded.

The system is designed around three pair-level verdicts:

- **CONGRUIT** — enough evidence that the two records represent the same transaction.
- **DISCREPAT** — enough evidence that the two records are different.
- **NON LIQUET** — the evidence is insufficient to establish either conclusion; a person decides.

Importantly, **"no match was found" is not the same as "the records are different."**  
A `DISCREPAT` verdict requires evidence supporting the difference.

---

## Example Question

> **"Why doesn't our cash book agree with the bank statement for June?"**

Liquet works backwards from the unexplained difference and gathers the evidence needed to explain it.

---

## How It Works

### 1. Load

Load the month's bank statement and the business's own cash records.

### 2. Match

Deterministic rules identify transactions that agree on defined criteria.

### 3. Connect

The graph layer links transactions to:

- their corresponding records;
- related records;
- explanations;
- previous and subsequent months;
- reconciliation history.

### 4. Investigate

The AI agent investigates remaining differences using controlled tools and the available evidence.

It can propose an explanation and, where appropriate, a correcting entry.

### 5. Approve

A person reviews the evidence and approves or rejects the proposed resolution.

The agent does not directly change the accounting records.

### 6. Record

Every step is logged so that the reconciliation can be reviewed later.

### 7. Learn Across Months

The following month, Liquet checks whether expected timing differences have actually cleared.

---

## Reconciliation Outcomes

At the **transaction-pair level**:

| Verdict | Meaning |
|---|---|
| `CONGRUIT` | Evidence supports that the two records are the same transaction |
| `DISCREPAT` | Evidence supports that the two records are different |
| `NON LIQUET` | Evidence is insufficient; a person decides |

At the **monthly reconciliation level**:

| Outcome | Meaning |
|---|---|
| `MATCHED` | Records have been reconciled |
| `EXPLAINED DIFFERENCE` | The difference has an identified explanation |
| `UNRESOLVED` | The available evidence does not establish an explanation |

Every verdict carries its supporting evidence.

---

## What It Tests

Liquet explores whether an AI agent is more reliable and easier to trace when it investigates reconciliation differences through a structured graph layer rather than working directly from raw records.

The system will be evaluated using **synthetic financial data containing known differences**, including timing differences, omissions, and errors.

The aim is not simply to ask whether the agent gets the answer right.

It is to examine:

- whether the agent reaches the correct explanation;
- whether the evidence supports its conclusion;
- whether the reasoning can be traced;
- when the agent correctly refuses to conclude;
- and whether the graph provides useful context for investigation.

---

## Why It Can Be Trusted

Liquet is designed around constrained automation rather than unrestricted AI decision-making.

- **Rules handle deterministic matches.**
- **The agent works through controlled tools.**
- **The agent cannot directly modify accounting records.**
- **Every verdict carries its evidence.**
- **`NON LIQUET` is an explicit and valid outcome.**
- **A person approves proposed resolutions.**
- **Every action is recorded in the audit trail.**

The system does not require the agent to always have an answer.

> **If the evidence is not sufficient, the correct answer is: `NON LIQUET`.**

---

# Dictionary

| Term | Latin meaning | Meaning in Liquet |
|---|---|---|
| **CONGRUIT** | "It agrees" | The two records represent the same transaction |
| **DISCREPAT** | "It differs" | There is sufficient evidence that the records are different |
| **NON LIQUET** | "It is not clear" | There is insufficient evidence; a person decides |
| **LIQUET** | "It is clear" | The reconciliation is fully explained; unreconciled amount is zero |
| **IN TRANSITU** | "In transit" | A timing difference expected to clear in a subsequent period |
| **OMISSUM** | "Something omitted" | A bank item missing from the cash book, or vice versa |
| **ERRATUM** | "An error" | An incorrect amount, date, reference, or other recorded value |
| **INDICIA** | "Signs / evidence" | Evidence attached to a verdict or explanation |
| **QUAESTOR** | Roman official associated with the treasury | The AI agent that investigates differences |
| **IUDEX** | "Judge" | The human reviewer who approves or rejects a proposed resolution |
| **NEXUS** | "Connection / bond" | The graph layer connecting records and their relationships |
| **ACTA** | "Records / proceedings" | The audit log recording the reconciliation process |

---

## Design Principle

Liquet does not replace the person responsible for the reconciliation.

It separates three things:

**Rules determine what can be established deterministically.**

**The agent investigates what remains.**

**The person decides when the evidence is insufficient.**

> **The system proposes. The evidence explains. The person approves.**