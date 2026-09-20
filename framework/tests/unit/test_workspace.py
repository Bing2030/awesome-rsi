import pytest

from rsif.artifacts.workspace import RunWorkspace, WorkspaceError
from rsif.config import RunConfig


def test_init_creates_layout(tmp_path):
    cfg = RunConfig()
    ws = RunWorkspace.init(tmp_path / "run", cfg.to_dict(), seed=7)
    assert ws.config_path.exists()
    assert ws.seed_path.exists()
    assert ws.artifacts_dir.is_dir()
    assert ws.evals_dir.is_dir()
    assert ws.cache_dir.is_dir()
    assert ws.config()["objective"] == "code-tasks"
    assert ws.seed() == 7


def test_init_refuses_nonempty(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    (root / "junk.txt").write_text("x")
    with pytest.raises(WorkspaceError):
        RunWorkspace.init(root, RunConfig().to_dict(), 0)


def test_open_validates(tmp_path):
    with pytest.raises(WorkspaceError):
        RunWorkspace.open(tmp_path / "missing")
