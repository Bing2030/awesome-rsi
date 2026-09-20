"""Shared fixtures: workspaces, deterministic clocks, offline guard."""

from __future__ import annotations

import socket

import pytest

from rsif.artifacts.workspace import RunWorkspace
from rsif.config import RunConfig


@pytest.fixture(autouse=True)
def offline_guard(monkeypatch, request):
    """Block all network in the default test run - accidental API calls fail loudly.
    Tests marked `live` opt into the network on purpose."""

    if request.node.get_closest_marker("live"):
        return

    def _blocked(*args, **kwargs):
        raise RuntimeError("network access is blocked in offline tests")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture
def fixed_clock():
    return lambda: 0.0


@pytest.fixture
def ws(tmp_path):
    cfg = RunConfig()
    workspace = RunWorkspace.init(tmp_path / "run", cfg.to_dict(), cfg.seed)
    return workspace


@pytest.fixture
def store(ws, fixed_clock):
    from rsif.artifacts.store import ArtifactStore

    return ArtifactStore(ws, clock=fixed_clock)
