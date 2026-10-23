"""config.py: settings from the environment, with defaults, never from .env in tests."""

from pathlib import Path

from liquet.config import DEFAULT_MODEL, DEFAULT_RUNS_DIR, load_settings


def test_nothing_set_gives_the_defaults():
    settings = load_settings({})
    assert settings.runs_dir == DEFAULT_RUNS_DIR
    assert settings.model == DEFAULT_MODEL


def test_the_environment_beats_the_default():
    settings = load_settings({"LIQUET_RUNS_DIR": "D:/liquet-runs", "LIQUET_MODEL": "some-model"})
    assert settings.runs_dir == Path("D:/liquet-runs")
    assert settings.model == "some-model"


def test_an_empty_value_counts_as_not_set():
    # LIQUET_MODEL= in a .env file means "not set", not "a model with no name".
    assert load_settings({"LIQUET_MODEL": ""}).model == DEFAULT_MODEL