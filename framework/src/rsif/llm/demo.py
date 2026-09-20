"""Offline demo provider: a deterministic stand-in for a real LLM.

`rsif init --provider scripted` workspaces run their whole lifecycle
(evolve / run / report) against DemoProvider - no network, no key, no cost,
fully deterministic. It plays every character of the self-improvement story:

- as the AGENT it answers coding tasks from a solution table, but only for
  the capabilities its active strategy prompt enables (a `STRATEGY-LEVEL: n`
  marker line in the evolved ``prompt/system``), so prompt evolution
  demonstrably changes agent behavior;
- as the IMPROVER it proposes a fixed sequence of bounded prompt edits -
  two genuine improvements, then a plausible-sounding regression that the
  validation gate must reject;
- as the REFLECTOR it returns a canned Reflexion-style lesson.

Matching is content-addressed (role + request text), never FIFO order, so
the demo script is robust to evaluation-order changes inside the engine.
"""

from __future__ import annotations

import json
import re

from rsif.llm.base import CompletionRequest, CompletionResult, LLMProvider
from rsif.llm.mock import text_result

# Reference solutions for every function in the shipped task packs
# (train/val/canary/test). Keys are the function names as declared in the
# task prompts.
SOLUTIONS: dict[str, str] = {
    # train
    "add": "def add(a, b):\n    return a + b\n",
    "is_even": "def is_even(n):\n    return n % 2 == 0\n",
    "reverse": "def reverse(s):\n    return s[::-1]\n",
    "max_of": "def max_of(a, b):\n    return a if a >= b else b\n",
    "factorial": "def factorial(n):\n    out = 1\n    for i in range(2, n + 1):\n        out *= i\n    return out\n",
    "count_vowels": 'def count_vowels(s):\n    return sum(1 for c in s.lower() if c in "aeiou")\n',
    "fib": "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n",
    "is_palindrome": 'def is_palindrome(s):\n    t = s.replace(" ", "").lower()\n    return t == t[::-1]\n',
    # val
    "sum_list": "def sum_list(xs):\n    total = 0\n    for x in xs:\n        total += x\n    return total\n",
    "gcd": "def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a\n",
    "flatten": "def flatten(xs):\n    out = []\n    for sub in xs:\n        out.extend(sub)\n    return out\n",
    "is_prime": "def is_prime(n):\n    if n < 2:\n        return False\n    i = 2\n    while i * i <= n:\n        if n % i == 0:\n            return False\n        i += 1\n    return True\n",
    "longest": "def longest(words):\n    best = words[0]\n    for w in words:\n        if len(w) > len(best):\n            best = w\n    return best\n",
    # test
    "unique": "def unique(xs):\n    out = []\n    for x in xs:\n        if x not in out:\n            out.append(x)\n    return out\n",
    "is_anagram": 'def is_anagram(a, b):\n    ca = sorted(a.replace(" ", "").lower())\n    cb = sorted(b.replace(" ", "").lower())\n    return ca == cb\n',
    "mean": "def mean(xs):\n    return sum(xs) / len(xs)\n",
    "binary_search": (
        "def binary_search(xs, x):\n"
        "    lo, hi = 0, len(xs) - 1\n"
        "    while lo <= hi:\n"
        "        mid = (lo + hi) // 2\n"
        "        if xs[mid] == x:\n"
        "            return mid\n"
        "        if xs[mid] < x:\n"
        "            lo = mid + 1\n"
        "        else:\n"
        "            hi = mid - 1\n"
        "    return -1\n"
    ),
    "capitalize_words": 'def capitalize_words(s):\n    return " ".join(w.capitalize() for w in s.split())\n',
}

# Capability per strategy level: the agent solves a task iff its function
# name is enabled at the active level. Level 1 = the seed prompt.
#   level 1: train 3/8, canary 3/3, val 3/5
#   level 2: train 6/8, canary 3/3, val 4/5   (accepted over level 1)
#   level 3: everything                       (accepted over level 2)
#   level 4: everything except `longest`      (plausible regression: val 4/5)
_ABILITY: dict[int, set[str]] = {
    1: {"add", "is_even", "reverse", "sum_list", "gcd", "flatten"},
    2: {"add", "is_even", "reverse", "max_of", "factorial", "count_vowels",
        "sum_list", "gcd", "flatten", "is_prime"},
    3: set(SOLUTIONS),
    4: set(SOLUTIONS) - {"longest"},
}

_STRATEGY_TAIL = {
    2: ("Worked example: restate the signature, enumerate edge cases (empty\n"
        "input, zero, one element), then implement the simplest loop-based\n"
        "solution.\n"),
    3: ("Worked example: restate the signature, enumerate edge cases (empty\n"
        "input, zero, one element), then implement the simplest loop-based\n"
        "solution. Verify your logic against every enumerated edge case\n"
        "before answering.\n"),
    4: ("Worked example: restate the signature, then implement the first\n"
        "solution that comes to mind; do not spend time on edge-case\n"
        "enumeration.\n"),
}


def strategy_prompt(level: int) -> str:
    """The evolved ``prompt/system`` content for a strategy level."""
    tail = _STRATEGY_TAIL.get(level, "")
    return (
        f"STRATEGY-LEVEL: {level}\n"
        "You are a careful Python-solving agent. Read the task, think, and answer with a\n"
        "single ```python code block implementing the requested function exactly\n"
        "(signature and name as specified). Prefer simple, correct, dependency-free\n"
        "code. The block must be self-contained: only stdlib imports.\n"
        f"{tail}"
    )


def _proposal(level: int, hypothesis: str, rationale: str) -> str:
    return json.dumps({
        "surface": "prompt",
        "operator": "prompt/refine",
        "hypothesis": hypothesis,
        "rationale": rationale,
        "ops": [{
            "op": "update",
            "artifact_id": "prompt/system",
            "payload": {"system.md": strategy_prompt(level)},
            "edit_kind": "replace",
        }],
    })


# The improver's proposal sequence: two verified improvements, then one
# plausible-sounding regression the validation gate must reject.
PROPOSALS: list[str] = [
    _proposal(2,
              "edge-case enumeration discipline reduces boundary failures",
              "the baseline loses iteration and aggregation tasks to off-by-one "
              "and edge-case mistakes"),
    _proposal(3,
              "verifying each enumerated edge case before answering "
              "generalizes further",
              "the level-2 strategy still fails tasks that need explicitly "
              "checked edge cases"),
    _proposal(4,
              "dropping edge-case enumeration produces faster, simpler answers",
              "the verbose discipline may be slowing the agent down without "
              "adding correctness"),
]

REFLECTION = (
    "The edit did not beat its parent on held-out validation; the apparent gain "
    "did not generalize. Next: propose a smaller, more targeted change and cite "
    "the specific failing capability."
)

_LEVEL_RE = re.compile(r"STRATEGY-LEVEL:\s*(\d+)")
_FN_RE = re.compile(r"`([A-Za-z_]\w*)\s*\(")


def _fence(code: str) -> str:
    return f"```python\n{code}\n```"


# -- exact-match objective character (M11 task-agnosticism) ---------------------
# Same mechanism (STRATEGY-LEVEL in the evolved prompt/system gates ability);
# different answer surface: plain exact text, no code fence.

_QA_QUESTIONS: list[tuple[str, str]] = [
    ("What is the capital of Japan?", "japan"),
    ("How many days are in a week?", "week"),
    ("What color do you get by mixing red and blue?", "purple"),
    ("What is 6 times 7?", "42"),
    ("Which planet is known as the Red Planet?", "mars"),
    ("How many continents are there?", "continents"),
    ("What is the chemical symbol for gold?", "gold"),
    ("What is 2 + 2?", "2+2"),
]

_QA_ANSWERS: dict[str, str] = {
    "japan": "Tokyo", "week": "7", "purple": "purple", "42": "42",
    "mars": "Mars", "continents": "7", "gold": "Au", "2+2": "4",
}

# Capability per level: baseline solves 2 train + canary + 1 val; level 2
# and 3 add facts; level 4 drops one val fact (a regression to reject).
_QA_ABILITY: dict[int, set[str]] = {
    1: {"japan", "week", "2+2", "mars"},
    2: {"japan", "week", "purple", "2+2", "mars", "continents"},
    3: set(_QA_ANSWERS),
    4: set(_QA_ANSWERS) - {"gold"},
}

_QA_STRATEGY_TAIL = {
    2: "Recall factual knowledge precisely; state the canonical answer verbatim.\n",
    3: "Recall factual knowledge precisely; state the canonical answer verbatim. "
       "Double-check the exact answer before responding.\n",
    4: "Answer quickly from first intuition; skip double-checking.\n",
}


def qa_strategy_prompt(level: int) -> str:
    tail = _QA_STRATEGY_TAIL.get(level, "")
    return (
        f"STRATEGY-LEVEL: {level}\n"
        "You are a concise question-answering agent. Answer with the exact "
        "answer text only - no explanation, no code block.\n"
        f"{tail}"
    )


def _qa_proposal(level: int, hypothesis: str, rationale: str) -> str:
    return json.dumps({
        "surface": "prompt",
        "operator": "prompt/refine",
        "hypothesis": hypothesis,
        "rationale": rationale,
        "ops": [{
            "op": "update",
            "artifact_id": "prompt/system",
            "payload": {"system.md": qa_strategy_prompt(level)},
            "edit_kind": "replace",
        }],
    })


QA_PROPOSALS: list[str] = [
    _qa_proposal(2, "precise factual recall reduces QA errors",
                 "the baseline misses some facts and gets others wrong"),
    _qa_proposal(3, "double-checking the exact answer generalizes further",
                 "the level-2 strategy still fails on harder facts"),
    _qa_proposal(4, "skipping double-checking gives faster answers",
                 "verbosity may be slowing responses without adding accuracy"),
]


class DemoProvider(LLMProvider):
    """Content-addressed scripted provider for offline demos.

    `objective` selects the agent character: "code-tasks" (code-fence
    solutions) or "exact-match" (plain-text answers). The improver and
    reflector roles are shared.
    """

    def __init__(self, objective: str = "code-tasks") -> None:
        self.objective = objective
        self.calls: list[CompletionRequest] = []
        self._improver_calls = 0

    # -- role dispatch --------------------------------------------------------

    def complete(self, req: CompletionRequest) -> CompletionResult:
        self.calls.append(req)
        if req.role == "improver":
            proposals = QA_PROPOSALS if self.objective == "exact-match" else PROPOSALS
            i = min(self._improver_calls, len(proposals) - 1)
            self._improver_calls += 1
            return text_result(proposals[i], model="demo")
        if req.role == "reflect":
            return text_result(REFLECTION, model="demo")
        return self._answer_as_agent(req)

    # -- the agent character --------------------------------------------------

    def _answer_as_agent(self, req: CompletionRequest) -> CompletionResult:
        system = next((m.content for m in req.messages if m.role == "system"), "")
        last_user = next(
            (m.content for m in reversed(req.messages) if m.role == "user"), "")
        level_match = _LEVEL_RE.search(system)
        level = int(level_match.group(1)) if level_match else 1
        if self.objective == "exact-match":
            return self._answer_qa(level, last_user)
        fn_match = _FN_RE.search(last_user)
        fn = fn_match.group(1) if fn_match else "f"
        if fn in SOLUTIONS and fn in _ABILITY.get(level, _ABILITY[1]):
            return text_result(_fence(SOLUTIONS[fn]), model="demo")
        # deterministic wrong answer: parses, runs, fails every hidden test
        return text_result(
            _fence(f"def {fn}(*args, **kwargs):\n    return None\n"),
            model="demo")

    def _answer_qa(self, level: int, last_user: str) -> CompletionResult:
        for question, key in _QA_QUESTIONS:
            if question in last_user:
                if key in _QA_ABILITY.get(level, _QA_ABILITY[1]):
                    return text_result(_QA_ANSWERS[key], model="demo")
                return text_result("not sure", model="demo")
        return text_result("not sure", model="demo")
