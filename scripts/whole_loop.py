"""The whole June loop, one command after another, exactly as a person would type them.

        python scripts/whole_loop.py            Claude's answers replayed from a real earlier run (free)
    python scripts/whole_loop.py --live     Claude really asked; stops before the person decides

    1. run the month                      python -m liquet.pipeline.run_month
    2. the graph after the rules          python -m liquet.graph.build_graph --snapshot   (..._rules)
    3. Claude investigates what is open   python -m liquet.review.investigate
    4. the graph with the proposals       python -m liquet.graph.build_graph --snapshot   (..._proposed)
    5. a person decides (demo)            python -m liquet.review.decide, once per decision
    6. the graph after review             python -m liquet.graph.build_graph --snapshot   (..._review)
    7. the score against the answer key   python -m liquet.evaluation.score

The decisions in step 5 are a DEMO, written for the replayed answers: in real use a
person reads each proposal and decides. With --live, Claude may answer differently,
so the loop stops after step 4 and leaves the deciding to you.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from liquet.config import load_settings

PROJECT = Path(__file__).parent.parent   # the project folder: scripts/ is one level down
JUNE = Path("tests") / "fixtures" / "2026-06"   # the commands run from the project folder
ANSWERS = JUNE / "claude_answers.jsonl"         # Claude's real answers from an earlier run

DECISIONS = [
    ["approve", "R2a:CE-2026-06-0004", "--reason", "15% withholding tax on the ATIT dividend"],
    ["approve", "R5:CE-2026-06-0011", "--reason", "trade settles 1 July, after the period"],
    ["approve", "P1", "--reason", "June custody fee per Northgate's fee notice"],
    ["approve", "P2", "--reason", "June credit interest per the bank statement"],
    ["approve", "P3", "--reason", "Amelia Hart's fee should be 437.50; digits swapped"],
]


def command(*args):
    """Run one Liquet command as if typed; print it and what it says; stop if it fails."""
    args = [str(a) for a in args]
    print(f"\n> python {' '.join(args)}")
    done = subprocess.run([sys.executable, *args], cwd=PROJECT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(done.stdout.rstrip())
    if done.returncode != 0:
        raise SystemExit(f"Stopped: {args[0]} failed.\n{done.stderr}")
    return done.stdout


def folder_after(text, output):
    """The folder a command says it saved to, e.g. 'Saved to runs/.../run-001'."""
    line = next(line for line in output.splitlines() if line.startswith(text))
    return Path(line.removeprefix(text).strip())


def main(runs, live=False):
    runs = Path(runs).resolve()   # the same folder wherever you start the script from
    print("1. Run the month")
    run = folder_after("Saved to", command(
                "-m", "liquet.pipeline.run_month", "--header", JUNE / "statement_header.json",
        "--lines", JUNE / "bank_statement.csv",
        "--accounts", JUNE / "firm" / "accounts.json",
        "--portfolios", JUNE / "firm" / "portfolios.json", "--runs", runs))

    print("\n2. The graph after the rules")
    snapshots = {"rules": folder_after("Snapshot saved to",
                                       command("-m", "liquet.graph.build_graph", run, "--snapshot"))}

    print("\n3. Claude investigates what the rules left open")
    if live:
        command("-m", "liquet.review.investigate", run)
    else:
        command("-m", "liquet.review.investigate", run, "--replay", ANSWERS)

    print("\n4. The graph with Claude's proposals")
    snapshots["proposed"] = folder_after("Snapshot saved to",
                                         command("-m", "liquet.graph.build_graph", run, "--snapshot"))
    if live:
        print(
            f"\nClaude has answered. Now you decide, with: "
            f"python -m liquet.review.decide {run} ..."
        )
        return {"run": run, "snapshots": snapshots}

    print("\n5. A person decides (demo)")
    for action, finding, *reason in DECISIONS:
        if "Saved:" not in command("-m", "liquet.review.decide", run, action, finding,
        "--by", "sonja", "--code", "CONFIRMED", *reason):
            raise SystemExit("Stopped: a decision was not saved.")

    print("\n6. The graph after review")
    snapshots["review"] = folder_after("Snapshot saved to",
                                       command("-m", "liquet.graph.build_graph", run, "--snapshot"))

    print("\n7. The score against the answer key")
    score = command("-m", "liquet.evaluation.score", run, JUNE / "answer_key.json")
    return {"run": run, "snapshots": snapshots, "score": score.strip().splitlines()[-1]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run, investigate, review and score June.")
    parser.add_argument("--runs", type=Path, help="where runs are saved (default: LIQUET_RUNS_DIR, else runs)")
    parser.add_argument("--live", action="store_true", help="really ask Claude (costs credits)")
    args = parser.parse_args()
    main(args.runs or load_settings().runs_dir, args.live)