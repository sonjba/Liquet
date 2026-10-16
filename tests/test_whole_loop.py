"""whole_loop.py: the review loop, run through the same commands a person types.

The other tests call the functions; this one runs the commands, so it also catches
what only breaks there: a wrong option, a message that points to the wrong folder,
a file Windows cannot save.
"""

import json

from whole_loop import main


def test_run_review_and_write_before_and_after(tmp_path, capsys):
    loop = main(tmp_path / "runs")
    printed = capsys.readouterr().out

    assert "54 nodes, 94 edges" in printed   # before review
    assert "57 nodes, 98 edges" in printed   # after: two decisions and the person

    assert loop["rules"].name.endswith("_rules")
    assert loop["review"].name.endswith("_review")
    assert loop["rules"].exists()            # the before snapshot is still there

    reviews = (loop["run"] / "reviews.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["kind"] for line in reviews] == ["APPROVED", "REJECTED"]

    # before, after = (json.loads(f.read_text(encoding="utf-8")) for f in loop["files"])
    # assert "Decision" not in before["nodes"]                     # no decision yet
    # assert [d["properties"]["kind"] for d in after["nodes"]["Decision"]] == [
    #     "APPROVED", "REJECTED"]