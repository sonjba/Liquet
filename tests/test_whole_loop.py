"""whole_loop.py: the June loop, run through the same commands a person types.

The other tests call the functions; this one runs the commands, so it also catches
what only breaks there: a wrong option, a message that points to the wrong folder,
a file Windows cannot save. Claude's answers are replayed, so it costs nothing.
"""

import json

from whole_loop import main


def test_run_investigate_review_and_score_june(tmp_path, capsys):
    loop = main(tmp_path / "runs")
    printed = capsys.readouterr().out

    assert "4 open items to investigate (0 already proposed)" in printed
    assert "CE-2026-06-0008: NON_LIQUET, nothing proposed" in printed
    assert "  Investigation   4" in printed
    assert [s.name.split("_")[-1] for s in loop["snapshots"].values()] == [
        "rules", "proposed", "review"]
    assert all(s.exists() for s in loop["snapshots"].values())   # none overwritten

    reviews = (loop["run"] / "reviews.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["kind"] for line in reviews] == ["APPROVED"] * 5
    investigations = (loop["run"] / "investigations.jsonl").read_text(encoding="utf-8")
    assert all(json.loads(line)["source"] == "replay:claude_answers.jsonl"
               for line in investigations.splitlines())
    assert loop["score"].split() == ["RIGHT:", "5", "WRONG:", "0", "OPEN:", "1"]