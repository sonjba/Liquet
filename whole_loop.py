"""The whole review loop on the June example, one command after another.

    python whole_loop.py

It runs exactly the commands a person would type, printing each one first:

    1. run the month                      run_month.py
    2. the graph before review            build_graph.py --snapshot      (..._rules)
    3. a person's decisions               decide.py, once per decision
    4. the graph after review             build_graph.py --snapshot      (..._review)
    5. each snapshot as readable JSON     graph_to_json.py

The decisions below are a DEMO: in real use a person reads the report and types
them. To try another decision, change DECISIONS. To add a step, add a command().
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).parent
JUNE = Path("tests") / "fixtures" / "2026-06"   # the commands run from the project folder

DECISIONS = [
    ["approve", "R5:CE-2026-06-0011", "--by", "sonja", "--code", "CONFIRMED"],
    ["reject", "R2a:CE-2026-06-0004", "--by", "sonja", "--code", "NEEDS_EVIDENCE",
     "--reason", "check the tax rate with the custodian"],
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


def main(runs):
    runs = Path(runs).resolve()   # the same folder wherever you start the script from
    print("1. Run the month")
    run = folder_after("Saved to", command(
        "run_month.py", "--header", JUNE / "statement_header.json",
        "--lines", JUNE / "bank_statement.csv",
        "--accounts", JUNE / "firm" / "accounts.json",
        "--portfolios", JUNE / "firm" / "portfolios.json", "--runs", runs))

    print("\n2. The graph before review")
    rules = folder_after("Snapshot saved to", command("build_graph.py", run, "--snapshot"))

    print("\n3. A person's decisions (demo)")
    for decision in DECISIONS:
        if "Saved:" not in command("decide.py", run, *decision):
            raise SystemExit("Stopped: a decision was not saved.")

    print("\n4. The graph after review")
    review = folder_after("Snapshot saved to", command("build_graph.py", run, "--snapshot"))

    # USED WHEN WE WANT TO SEE GRAPH AS JSON
    # print("\n5. Each snapshot as readable JSON")
    # files = []
    # for snapshot in (rules, review):
    #     command("graph_to_json.py", snapshot)
    #     files.append(snapshot.with_name(snapshot.name + ".json"))

    print("\nDone. Open these side by side (a picture: python show_graph.py <snapshot folder>):")
    
    # USED WHEN WE WANT TO SEE GRAPH AS JSON
    # for file in files:
    #     print(f"  {file}")
    # return {"run": run, "rules": rules, "review": review, "files": files}
    return {"run": run, "rules": rules, "review": review}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run, review and draw the June example.")
    parser.add_argument("--runs", type=Path, default=Path("runs"), help="where runs are saved")
    main(parser.parse_args().runs)