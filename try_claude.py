import anthropic
from dotenv import load_dotenv
import json
from datetime import datetime, timezone
from pathlib import Path
from propose import record_proposal
import sys
from facts import facts_for

load_dotenv()
client = anthropic.Anthropic()

job = """You are Quaestor, the investigator in Liquet, a monthly bank reconciliation.
Use only the facts you are given. If they are not enough, say so.
You suggest an explanation; a person decides.
The rules have already tried these, so do not suggest them again:
- R1: same reference, same amount, dates at most 1 day apart.
- R2a: an overseas dividend paid net of withholding tax.
- R3: one bank line paying several entries that share its reference.
- R4: no reference; same amount and type, dates at most 1 day apart;
  if the bank text names one client, that client's entry wins.
- R5: a trade that settles after the month ends.
An open item is one none of these could explain.
A match a rule made is settled; explain only what is still open."""

run = sorted(Path(r"runs\ACC-KRW-CASH-01_2026-06").glob("run-*"))[-1]
item_id = sys.argv[1]

facts = facts_for(run, item_id)
question = ("Facts gathered by Liquet:\n" + json.dumps(facts, indent=2) +
            "\n\nPropose an explanation, or answer NON_LIQUET if the facts are not enough.")

form = {
    "type": "object",
    "properties": {
        "answer":      {"type": "string", "enum": ["PROPOSAL", "NON_LIQUET"]},
        "category":    {"type": "string", "enum": ["IN_TRANSITU", "OMISSUM", "ERRATUM", ""]},
        "type":        {"type": "string", "enum": ["DEPOSIT_IN_TRANSIT", "OUTSTANDING_PAYMENT",
                                                   "OUTSTANDING_RECEIPT", "BANK_FEE", "INTEREST",
                                                   "WITHHOLDING_TAX", "BOOK_ERROR", ""]},
        "adjusts":     {"type": "string", "enum": ["book", "bank", ""]},
        "adjustment":  {"type": "string",
                        "description": "only a signed amount with two decimals, e.g. -45.00; empty for NON_LIQUET"},
        "explanation": {"type": "string"},
    },
    "required": ["answer", "category", "type", "adjusts", "adjustment", "explanation"],
    "additionalProperties": False,
}
response = client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=1024,
    system=job,
    messages=[{"role": "user", "content": question}],
    output_config={"format": {"type": "json_schema", "schema": form}},
)

for block in response.content:
    if block.type == "text":
        answer = json.loads(block.text)
        print(json.dumps(answer, indent=2))
print("tokens in:", response.usage.input_tokens, "out:", response.usage.output_tokens)
print("stopped because:", response.stop_reason)



if answer["answer"] == "PROPOSAL":
    try:
        proposal = record_proposal(
            run, [item_id],
            answer["category"], answer["type"], answer["adjusts"],
            answer["adjustment"], answer["explanation"],
            by="quaestor", proposer="agent", at=datetime.now(timezone.utc),
            evidence=facts,
            model="claude-sonnet-5-5")
        print("Saved as", proposal["proposal_id"])
    except ValueError as error:
        print("Refused by the checks:", error)
else:
    print("Claude says NON LIQUET; nothing saved")