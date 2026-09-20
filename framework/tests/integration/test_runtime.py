"""M4 verification: runtime executes a scripted agent; loader validates ABI."""

import pytest

from rsif.llm.mock import ScriptedProvider, text_result
from rsif.objectives.base import Split
from rsif.objectives.code_tasks import CodeTasksObjective
from rsif.runtime.loader import ModuleLoadError, load_module_source
from rsif.runtime.runtime import AgentRuntime
from rsif.spec import AgentSpec


def _spec() -> AgentSpec:
    return AgentSpec(
        system_prompt="Solve coding tasks. Answer with a ```python fence.",
    )


def test_scripted_agent_solves_tasks(tmp_path):
    obj = CodeTasksObjective()
    train = obj.suites()[Split.TRAIN].tasks

    provider = ScriptedProvider()
    # one correct answer per task, matched on the task prompt
    for t in train[:3]:
        fn = t.meta["function_name"]
        provider.add("agent", t.prompt, text_result(
            f"```python\n{_SOLUTION(fn)}\n```"))

    runtime = AgentRuntime(provider)
    passed = 0
    for t in train[:3]:
        attempt = runtime.run(t.prompt, _spec())
        score = obj.evaluate(t, attempt)
        passed += score.score

    assert passed == 3
    assert len(provider.calls) == 3


def test_trace_and_usage_recorded():
    provider = ScriptedProvider().add(
        "agent", "TASK", text_result("```python\ndef f():\n    return 1\n```"))
    runtime = AgentRuntime(provider)
    attempt = runtime.run("TASK", _spec())
    assert attempt.result.startswith("```python")
    assert attempt.usage.out_tokens > 0
    assert [s.kind for s in attempt.trace] == ["llm_call", "submit"]


def test_module_loader_rejects_non_abi():
    with pytest.raises(ModuleLoadError):
        load_module_source("x = 1\n")  # no Module class


def test_module_loader_rejects_forbidden_import():
    with pytest.raises(ModuleLoadError):
        load_module_source("import os\nclass Module:\n    pass\n")


def test_custom_module_drives_loop():
    # a module that always submits a fixed answer
    source = '''\
from rsif.runtime.module_api import AgentModule, ModuleContext, SubmitAction, Action


class Module(AgentModule):
    def step(self, ctx: ModuleContext) -> Action:
        return SubmitAction("```python\\ndef answer():\\n    return 42\\n```")
'''
    spec = _spec()
    spec.module_source = source
    provider = ScriptedProvider()  # must never be called
    runtime = AgentRuntime(provider)
    attempt = runtime.run("ignored", spec)
    assert attempt.result == "```python\ndef answer():\n    return 42\n```"
    assert len(provider.calls) == 0


def _SOLUTION(fn: str) -> str:
    return {
        "add": "def add(a, b):\n    return a + b\n",
        "is_even": "def is_even(n):\n    return n % 2 == 0\n",
        "reverse": "def reverse(s):\n    return s[::-1]\n",
        "max_of": "def max_of(a, b):\n    return a if a >= b else b\n",
        "factorial": "def factorial(n):\n    r = 1\n    for i in range(1, n + 1):\n        r *= i\n    return r\n",
        "count_vowels": "def count_vowels(s):\n    return sum(1 for c in s.lower() if c in 'aeiou')\n",
        "is_palindrome": "def is_palindrome(s):\n    t = s.replace(' ', '').lower()\n    return t == t[::-1]\n",
        "fib": "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n",
    }[fn]
