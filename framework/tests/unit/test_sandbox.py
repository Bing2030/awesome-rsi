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


def test_scan_syntax_error():
    report = scan_code("def broken(:\n")
    assert not report.safe
    assert "syntax error" in report.violations[0]
