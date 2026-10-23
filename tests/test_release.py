"""release.py: which code produced a result, recorded with every run."""

from importlib.metadata import version

import liquet.release as release


def test_it_names_the_version_and_the_commit():
    info = release.release_info()
    assert info["liquet_version"] == version("liquet")
    assert len(info["git_commit"]) == 40            # a full commit hash
    assert info["uncommitted_changes"] in (True, False)


def test_outside_a_git_checkout_it_says_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "CODE_FOLDER", tmp_path)    # no .git here
    info = release.release_info()
    assert info["git_commit"] == "unknown"
    assert info["uncommitted_changes"] is None