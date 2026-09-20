"""Sandboxed execution for agent-written code, skill self-tests, and eval.

One code path (subprocess + `python -I` + timeouts + rlimits) runs everything
the framework executes, so the failure modes are exercised in tests.

Grounding: verification must be execution-grounded [arXiv 2310.01798,
2305.11738]; DGM's "self-edits can introduce bugs that must be caught by the
evaluator" [arXiv 2505.22954].
"""
