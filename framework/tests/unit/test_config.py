import pytest

import rsif
from rsif.config import ConfigError, RunConfig


def test_package_imports():
    assert rsif.__version__


def test_defaults_valid():
    RunConfig()


def test_invalid_provider_rejected():
    with pytest.raises(ConfigError):
        RunConfig(provider="nope")


def test_objective_names_are_open():
    """Task-agnostic seam: RunConfig accepts any objective name — built-in
    dispatch happens in objective_from_config, and projects/tests hand the
    engine a hand-constructed Objective (M14: the closed set contradicted
    the engine's own structural guarantee)."""
    assert RunConfig(objective="regex-tasks").objective == "regex-tasks"
    with pytest.raises(ConfigError):
        RunConfig(objective="")


def test_roundtrip():
    cfg = RunConfig(model="claude-sonnet-5", acceptance_threshold=0.05)
    cfg.extra["custom_flag"] = 1
    data = cfg.to_dict()
    restored = RunConfig.from_dict(data)
    assert restored.model == "claude-sonnet-5"
    assert restored.acceptance_threshold == 0.05
    assert restored.extra == {"custom_flag": 1}


def test_resolved_model_roles():
    cfg = RunConfig(model="m1", improver_model="m2")
    assert cfg.resolved_model() == "m1"
    assert cfg.resolved_model("improver") == "m2"
