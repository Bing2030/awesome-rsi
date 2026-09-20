"""Subprocess sandbox for running untrusted Python in a controlled way.

No Docker on macOS dev machines: `python -I` (isolated, ignores PYTHONPATH and
user site), a fresh temp cwd, wall-clock + CPU timeouts, and best-effort
rlimits (CPU authoritative; address-space best-effort). Any crash/timeout/non
zero exit is mapped to an ExecutionOutcome with the error text kept for
reflection.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass


@dataclass
class ExecutionOutcome:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    wall_s: float = 0.0

    @property
    def error_text(self) -> str:
        if self.timed_out:
            return "timeout"
        return (self.stderr or self.stdout or f"exit code {self.exit_code}").strip()


def _apply_limits(proc_kwargs: dict, timeout_s: float, mem_mb: int) -> None:
    """Best-effort resource limits; CPU time is the authoritative bound."""
    if sys.platform != "win32":
        import resource

        def _limit():
            # CPU seconds (authoritative), address space (best-effort on macOS)
            resource.setrlimit(resource.RLIMIT_CPU, (int(timeout_s) + 1, int(timeout_s) + 1))
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024,) * 2)
            except (ValueError, OSError):
                pass

        proc_kwargs["preexec_fn"] = _limit


def run_python(
    source: str,
    *,
    stdin: str = "",
    timeout_s: float = 10.0,
    mem_mb: int = 512,
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> ExecutionOutcome:
    """Run `source` as a Python program in a temp dir, return its outcome.

    The child gets a minimal environment (PATH only): untrusted evolved code
    must not see secrets such as API keys. Residual limitation, documented:
    network egress from the child is NOT blocked (no seccomp on macOS) - the
    scrubbed env removes the exfiltration prize, not the socket.
    """
    with tempfile.TemporaryDirectory() as td:
        script = os.path.join(td, "main.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(source)

        kwargs: dict = dict(
            args=[sys.executable, "-I", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd or td,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                 **(extra_env or {})},
        )
        _apply_limits(kwargs, timeout_s, mem_mb)

        start = time.monotonic()
        try:
            proc = subprocess.run(
                input=stdin.encode("utf-8"),
                timeout=timeout_s,
                **kwargs,
            )
            wall = time.monotonic() - start
            return ExecutionOutcome(
                ok=proc.returncode == 0,
                exit_code=proc.returncode,
                stdout=proc.stdout.decode("utf-8", errors="replace"),
                stderr=proc.stderr.decode("utf-8", errors="replace"),
                wall_s=wall,
            )
        except subprocess.TimeoutExpired:
            return ExecutionOutcome(
                ok=False, exit_code=-1, stdout="", stderr="",
                timed_out=True, wall_s=timeout_s,
            )
