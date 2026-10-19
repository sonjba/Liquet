"""Ask Claude about the open items the rules left: tier 1, one call per item.

    python investigate.py RUN                    every open item not already proposed
    python investigate.py RUN ITEM_ID            one item
    python investigate.py RUN --replay FILE      reuse answers Claude gave before (free)

Code gathers the facts (facts.py), Claude answers in a fixed form, propose.py checks
the answer before it is saved as a proposal for a person to decide. Every call,
NON_LIQUET included, is logged in RUN/investigations.jsonl.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import anthropic
from dotenv import load_dotenv

from liquet.review.decide import load_reviews
from liquet.review.facts import facts_for
from liquet.review.propose import load_proposals, record_proposal
from liquet.review.work_list import open_items

MODEL = "claude-sonnet-5-5"

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


def already_proposed(run):
    """Open items that have a proposal waiting for a person, or one a person approved."""
    reviews = {review["finding_id"]: review["kind"] for review in load_reviews(run)}
    return {item_id for proposal in load_proposals(run)
            if reviews.get(proposal["proposal_id"]) != "REJECTED"
            for item_id in proposal["item_ids"]}


class ReplayClaude:
    """Gives back answers Claude really gave before, read from an investigations.jsonl.
    It costs nothing and gives the same result every time: for the whole loop and tests.
    It answers client.messages.create(...) like the real client, with only the parts
    investigate() reads."""

    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.answers = {line["item_id"]: line for line in lines}   # the latest per item
        self.messages = self

    def create(self, **request):
        question = request["messages"][0]["content"]
        for item_id, logged in self.answers.items():
            if f'"item_id": "{item_id}"' in question:
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=json.dumps(logged["answer"]))],
                    usage=SimpleNamespace(input_tokens=logged["input_tokens"],
                                          output_tokens=logged["output_tokens"]),
                    stop_reason=logged["stop_reason"])
        raise ValueError("the replay file has no answer for this question's open item")


def investigate(client, run, item_id, source="claude"):
    """One call to Claude about one open item; the answer checked, saved and logged.
    `source` says where the answer came from: "claude", or "replay:<file>"."""
    facts = facts_for(run, item_id)
    examined = facts.pop("examined")          # ids for the graph; Claude reads the sentences
    question = ("Facts gathered by Liquet:\n" + json.dumps(facts, indent=2) +
                "\n\nPropose an explanation, or answer NON_LIQUET if the facts are not enough.")

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=job,
        messages=[{"role": "user", "content": question}],
        output_config={"format": {"type": "json_schema", "schema": form}},
    )
    for block in response.content:
        if block.type == "text":
            answer = json.loads(block.text)

    proposal_id = None
    if answer["answer"] == "PROPOSAL":
        try:
            proposal = record_proposal(
                run, [item_id],
                answer["category"], answer["type"], answer["adjusts"],
                answer["adjustment"], answer["explanation"],
                by="quaestor", proposer="agent", at=datetime.now(timezone.utc),
                evidence=facts,
                model=MODEL)
            proposal_id = proposal["proposal_id"]
            outcome = f"saved as {proposal_id}"
        except ValueError as error:
            outcome = f"refused by the checks: {error}"
    else:
        outcome = "NON_LIQUET, nothing proposed"

    investigation = {"at": datetime.now(timezone.utc).isoformat(), "item_id": item_id,
                     "by": "quaestor", "examined": examined, "source": source,
                     "model": MODEL, "job": job, "question": question,
                     "answer": answer, "outcome": outcome, "proposal_id": proposal_id,
                     "input_tokens": response.usage.input_tokens,
                     "output_tokens": response.usage.output_tokens,
                     "stop_reason": response.stop_reason}
    with open(run / "investigations.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(investigation) + "\n")
    return investigation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask Claude about a run's open items.")
    parser.add_argument("run_folder", type=Path)
    parser.add_argument("item_id", nargs="?", help="one item; leave out for all open items")
    parser.add_argument("--replay", type=Path,
                        help="reuse answers from an investigations.jsonl instead of calling Claude")
    args = parser.parse_args()
    run = args.run_folder

    if args.replay:
        client, source = ReplayClaude(args.replay), f"replay:{args.replay.name}"
    else:
        load_dotenv()
        client, source = anthropic.Anthropic(), "claude"

    if args.item_id:
        item_ids = [args.item_id]
    else:
        skip = already_proposed(run)
        item_ids = [item["item_id"] for item in open_items(run) if item["item_id"] not in skip]
        print(f"{len(item_ids)} open items to investigate ({len(skip)} already proposed)")

    for item_id in item_ids:
        investigation = investigate(client, run, item_id, source)
        print(f"{item_id}: {investigation['outcome']}")
        print(f"  {investigation['answer']['explanation']}")
        print(f"  tokens in {investigation['input_tokens']}, out {investigation['output_tokens']}")