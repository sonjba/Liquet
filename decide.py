"""A person's decisions on a run's findings and proposals: approve or reject.

    python decide.py RUN approve R5:CE-2026-06-0011 --by sonja --code CONFIRMED
    python decide.py RUN reject R2a:CE-2026-06-0004 --by sonja --code NEEDS_EVIDENCE \
        --reason "check the tax rate with the custodian"

Every decision has a reason code from REASON_CODES (so reasons can be counted
and learned from) and, when it rejects, a reason in words.

Each decision is one line added to RUN/reviews.jsonl. Lines are only ever
added, never changed, so the file is the history of the review.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from run_store import load_run

REVIEWS = "reviews.jsonl"
REASON_CODES = ("CONFIRMED", "WRONG_AMOUNT", "WRONG_PERIOD", "WRONG_PARTY",
                "NEEDS_EVIDENCE", "OTHER")


def load_reviews(run_folder: Path) -> list[dict]:
    """Every decision made on this run so far, oldest first."""
    path = Path(run_folder) / REVIEWS
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def record(run_folder: Path, kind: str, finding_id: str, by: str, at: datetime,
           reason_code: str, reason: str = "") -> dict:
    """Check one decision, then add it to the end of reviews.jsonl."""
    from propose import load_proposals  # imported here: propose.py imports this module
    findings = {f["finding_id"] for f in load_run(run_folder)["findings"]}
    findings |= {p["proposal_id"] for p in load_proposals(run_folder)}
    decided = {r["finding_id"] for r in load_reviews(run_folder)}
    if kind not in ("APPROVED", "REJECTED"):
        raise ValueError(f"a decision is APPROVED or REJECTED, not {kind!r}")
    if finding_id not in findings:
        raise ValueError(f"this run has no finding or proposal {finding_id!r}")
    if finding_id in decided:
        raise ValueError(f"{finding_id} is already decided")
    if reason_code not in REASON_CODES:
        raise ValueError(f"reason code must be one of {', '.join(REASON_CODES)}")
    if kind == "REJECTED" and not reason:
        raise ValueError("a rejection needs a reason")

    review = {"kind": kind, "finding_id": finding_id, "by": by, "at": at.isoformat(),
              "reason_code": reason_code, "reason": reason}
    with open(Path(run_folder) / REVIEWS, "a", encoding="utf-8") as f:
        f.write(json.dumps(review) + "\n")
    return review


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Approve or reject a finding or a proposal.")
    parser.add_argument("run_folder", type=Path)
    parser.add_argument("action", choices=["approve", "reject"])
    parser.add_argument("finding_id")
    parser.add_argument("--by", required=True, help="your name")
    parser.add_argument("--code", required=True, choices=REASON_CODES, help="reason code")
    parser.add_argument("--reason", default="", help="in words; needed when you reject")
    args = parser.parse_args()

    kind = "APPROVED" if args.action == "approve" else "REJECTED"
    try:
        review = record(args.run_folder, kind, args.finding_id, args.by,
                        datetime.now(timezone.utc), args.code, args.reason)
        print(f"Saved: {review['finding_id']} {review['kind']} by {review['by']}")
    except ValueError as error:
        print(f"Not saved: {error}")