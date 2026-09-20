"""M2 verification: protocol, mocks, cache, adapter serialization."""

import pytest

from rsif.llm.base import (
    CompletionRequest,
    Message,
    ToolSpec,
    extract_code_fence,
)
from rsif.llm.mock import EchoProvider, ScriptedProvider, text_result, tool_result


def _req(text, role="agent", tools=()):
    return CompletionRequest(
        messages=(Message("system", "sys"), Message("user", text)),
        role=role, tools=tools,
    )


def test_scripted_provider_matches_and_pops():
    p = ScriptedProvider().add("agent", "hello", text_result("world"))
    r = p.complete(_req("say hello there"))
    assert r.text == "world"
    # queue drained -> next call fails
    with pytest.raises(AssertionError):
        p.complete(_req("hello again"))


def test_scripted_provider_role_isolation():
    p = ScriptedProvider({
        "agent": [("a", text_result("A"))],
        "improver": [("b", text_result("B"))],
    })
    assert p.complete(_req("...a...", role="agent")).text == "A"
    assert p.complete(_req("...b...", role="improver")).text == "B"


def test_scripted_no_match_raises():
    p = ScriptedProvider().add("agent", "needle", text_result("x"))
    with pytest.raises(AssertionError):
        p.complete(_req("completely unrelated text"))


def test_echo_provider_extracts_code():
    p = EchoProvider()
    r = p.complete(_req("write:\n```python\ndef f():\n    return 1\n```\nthanks"))
    assert "def f()" in r.text


def test_extract_code_fence_fallback():
    assert extract_code_fence("no fence") == "no fence"
    assert extract_code_fence("```python\nx=1\n```\nrest") == "x=1"


def test_cache_hit_and_miss(tmp_path):
    from rsif.llm.cache import CachedProvider, ResponseCache

    inner = ScriptedProvider().add("agent", "q", text_result("answer"))
    cached = CachedProvider(inner, ResponseCache(tmp_path / "c"), name="scripted")

    req = _req("q")
    r1 = cached.complete(req)
    assert cached.misses == 1
    r2 = cached.complete(req)  # identical request -> cache hit, inner not called
    assert r2.text == "answer"
    assert cached.hits == 1
    assert cached.misses == 1


def test_cache_tool_calls_roundtrip(tmp_path):
    from rsif.llm.cache import CachedProvider, ResponseCache

    inner = ScriptedProvider().add("agent", "q", tool_result("toolx", '{"a": 1}'))
    cached = CachedProvider(inner, ResponseCache(tmp_path / "c"), name="scripted")
    req = _req("q")
    r1 = cached.complete(req)
    r2 = cached.complete(req)
    assert r2.tool_calls[0].name == "toolx"
    assert r2.tool_calls[0].arguments == '{"a": 1}'


# -- adapter serialization (stubbed SDK clients, no network) ----------------

class _StubMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _StubChoice:
    def __init__(self, message, finish_reason="stop"):
        self.message = message
        self.finish_reason = finish_reason


class _StubResp:
    def __init__(self, message, usage, model="m", finish_reason="stop"):
        self.choices = [_StubChoice(message, finish_reason)]
        self.usage = usage
        self.model = model


def test_openai_provider_serialization():
    from rsif.llm.openai_provider import OpenAIProvider

    class _U:
        prompt_tokens = 3
        completion_tokens = 5

    class _TC:
        def __init__(self):
            self.id = "id1"
            self.function = type("F", (), {"name": "f", "arguments": "{}"})()

    captured = {}

    class _Client:
        def __init__(self):
            self.chat = type("C", (), {"completions": type(
                "CC", (), {"create": self._create})()})()

        def _create(self, **kwargs):
            captured["kwargs"] = kwargs
            return _StubResp(_StubMessage("hi", [_TC()]), _U(), "m1", "tool_calls")

    p = OpenAIProvider(model="m", client=_Client())
    r = p.complete(_req("hello", tools=(ToolSpec("f", "d", '{"type":"object"}'),)))
    assert r.text == "hi"
    assert r.tool_calls[0].name == "f"
    assert r.usage.in_tokens == 3 and r.usage.out_tokens == 5
    assert captured["kwargs"]["model"] == "m"
    assert captured["kwargs"]["tools"][0]["type"] == "function"


def test_anthropic_provider_serialization():
    from rsif.llm.anthropic_provider import AnthropicProvider

    class _Block:
        def __init__(self, type, text="", name="", id="", input=None):
            self.type = type
            self.text = text
            self.name = name
            self.id = id
            self.input = input

    captured = {}

    class _Resp:
        model = "m2"
        stop_reason = "tool_use"
        content = [_Block("text", text="answer"), _Block("tool_use", name="run", id="i1", input={"x": 1})]
        usage = type("U", (), {"input_tokens": 2, "output_tokens": 4})()

    class _Messages:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return _Resp()

    class _Client:
        def __init__(self):
            self.messages = _Messages()

    p = AnthropicProvider(model="m", client=_Client())
    r = p.complete(_req("hello", tools=(ToolSpec("run", "d", '{"type":"object"}'),)))
    assert r.text == "answer"
    assert r.tool_calls[0].name == "run"
    assert captured["kwargs"]["system"] == "sys"
    assert captured["kwargs"]["tools"][0]["name"] == "run"
