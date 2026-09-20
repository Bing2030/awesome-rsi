"""M3 verification: sandbox limits + static guard scan."""

from rsif.sandbox.exec import run_python
from rsif.sandbox.guards import scan_code


def test_ok_program_runs():
    out = run_python("print('hi')")
    assert out.ok and out.exit_code == 0 and "hi" in out.stdout


def test_infinite_loop_killed():
    out = run_python("while True:\n    pass", timeout_s=1.0)
    assert not out.ok and out.timed_out


def test_memory_hog_killed():
    # allocate aggressively; address-space limit or CPU wall will stop it
    out = run_python(
        "x = bytearray()\n"
        "while True:\n"
        "    x.extend(b'0' * 1024 * 1024)\n",
        timeout_s=2.0, mem_mb=64)
    assert not out.ok


def test_exception_mapped_to_error_text():
    out = run_python("raise ValueError('boom')")
    assert not out.ok and "boom" in out.error_text


def test_scan_flags_os_system():
    report = scan_code("import os\nos.system('ls')\n")
    assert not report.safe
    assert any("os" in v for v in report.violations)


def test_scan_flags_subprocess():
    assert not scan_code("import subprocess\nsubprocess.run(['ls'])").safe


def test_scan_flags_framework_import():
    assert not scan_code("from rsif.artifacts import store").safe


def test_scan_allows_stdlib_math():
    assert scan_code("import math\nx = math.sqrt(4)\n").safe


def test_scan_whitelist_blocks_transitive_attribute_escape():
    """The blacklist era was bypassable: `from rsif.commands import os` bound
    a forbidden module via a trusted framework module's attribute. The
    whitelist must reject every rsif import except the module ABI."""
    assert not scan_code("from rsif.commands import os\n").safe
    assert not scan_code("from rsif.config import json\n").safe
    assert not scan_code("import rsif.commands\n").safe
    assert not scan_code("from rsif.runtime.runtime import AgentRuntime\n").safe


def test_scan_allows_module_abi_import():
    src = ("from rsif.runtime.module_api import (\n"
           "    AgentModule, LLMAction, ModuleContext, SubmitAction)\n")
    assert scan_code(src).safe


def test_scan_flags_non_whitelisted_stdlib():
    assert not scan_code("import socket\n").safe
    assert not scan_code("import sys\n").safe
    assert not scan_code("from pathlib import Path\n").safe


def test_sandbox_child_env_has_no_secrets():
    """Untrusted evolved code must not see the parent's environment."""
    import os

    was = os.environ.get("RSIF_SECRET_PROBE")
    os.environ["RSIF_SECRET_PROBE"] = "s3cret"
    try:
        out = run_python(
            "import os\nprint(os.environ.get('RSIF_SECRET_PROBE', 'ABSENT'))")
        assert out.ok and "ABSENT" in out.stdout and "s3cret" not in out.stdout
        # PATH is preserved so the interpreter itself stays findable
        out2 = run_python("import os\nprint('PATH' in os.environ)")
        assert out2.ok and "True" in out2.stdout
    finally:
        if was is None:
            os.environ.pop("RSIF_SECRET_PROBE", None)
        else:
            os.environ["RSIF_SECRET_PROBE"] = was


def test_scan_syntax_error():
    report = scan_code("def broken(:\n")
    assert not report.safe
    assert "syntax error" in report.violations[0]
