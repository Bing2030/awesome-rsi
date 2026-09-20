"""Generate the seed task packs for the code-tasks objective.

Run once: `uv run python scripts/gen_seed_tasks.py`.
Output: src/rsif/objectives/tasks/{train,val,test,canary}/NN.json

Each task: {id, prompt, function_name, hidden_tests}. The hidden_tests source
is appended to the agent's submitted code and executed in the sandbox; the
task passes iff the combined program exits 0 (all asserts pass).

Deterministic and stdlib-only - these are the v1 seed packs (can grow).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent / "src" / "rsif" / "objectives" / "tasks"

# (function_name, prompt, hidden_tests) — tests are asserts, no imports needed.
TASKS = {
    "train": [
        ("add", "Implement a function `add(a, b)` that returns a + b.",
         "assert add(2, 3) == 5\nassert add(-1, 1) == 0\nassert add(0, 0) == 0\n"),
        ("is_even", "Implement a function `is_even(n)` returning True iff n is even.",
         "assert is_even(4) is True\nassert is_even(3) is False\nassert is_even(0) is True\n"),
        ("reverse", "Implement `reverse(s)` returning the string reversed.",
         "assert reverse('abc') == 'cba'\nassert reverse('') == ''\nassert reverse('a') == 'a'\n"),
        ("max_of", "Implement `max_of(a, b)` returning the larger of two numbers.",
         "assert max_of(3, 5) == 5\nassert max_of(5, 3) == 5\nassert max_of(2, 2) == 2\n"),
        ("factorial", "Implement `factorial(n)` returning n! for n >= 0.",
         "assert factorial(0) == 1\nassert factorial(1) == 1\nassert factorial(5) == 120\n"),
        ("count_vowels", "Implement `count_vowels(s)` counting aeiou (case-insensitive).",
         "assert count_vowels('hello') == 2\nassert count_vowels('AEIOU') == 5\nassert count_vowels('xyz') == 0\n"),
        ("is_palindrome", "Implement `is_palindrome(s)` (ignore case and spaces).",
         "assert is_palindrome('racecar') is True\nassert is_palindrome('A man a plan a canal panama'.replace(' ', '').lower()) is True\nassert is_palindrome('hello') is False\n"),
        ("fib", "Implement `fib(n)` returning the nth Fibonacci number (fib(0)=0, fib(1)=1).",
         "assert fib(0) == 0\nassert fib(1) == 1\nassert fib(10) == 55\n"),
    ],
    "val": [
        ("sum_list", "Implement `sum_list(xs)` summing a list of numbers.",
         "assert sum_list([1, 2, 3]) == 6\nassert sum_list([]) == 0\nassert sum_list([-1, 1]) == 0\n"),
        ("gcd", "Implement `gcd(a, b)` via the Euclidean algorithm.",
         "assert gcd(48, 18) == 6\nassert gcd(7, 5) == 1\nassert gcd(0, 5) == 5\n"),
        ("flatten", "Implement `flatten(xs)` flattening one level of nesting.",
         "assert flatten([[1, 2], [3], []]) == [1, 2, 3]\nassert flatten([]) == []\n"),
        ("is_prime", "Implement `is_prime(n)` for n >= 2.",
         "assert is_prime(2) is True\nassert is_prime(4) is False\nassert is_prime(17) is True\n"),
        ("longest", "Implement `longest(words)` returning the longest string in a list.",
         "assert longest(['a', 'bb', 'ccc']) == 'ccc'\nassert longest(['x']) == 'x'\n"),
    ],
    "test": [
        ("unique", "Implement `unique(xs)` returning a list with duplicates removed (preserve order).",
         "assert unique([1, 2, 2, 3, 1]) == [1, 2, 3]\nassert unique([]) == []\n"),
        ("binary_search", "Implement `binary_search(xs, x)` returning the index of x in a sorted list, or -1.",
         "assert binary_search([1, 3, 5, 7], 5) == 2\nassert binary_search([1, 3, 5, 7], 9) == -1\nassert binary_search([], 1) == -1\n"),
        ("anagram", "Implement `is_anagram(a, b)` ignoring case and spaces.",
         "assert is_anagram('listen', 'silent') is True\nassert is_anagram('hello', 'world') is False\n"),
        ("mean", "Implement `mean(xs)` returning the arithmetic mean of a non-empty list.",
         "assert abs(mean([1, 2, 3, 4]) - 2.5) < 1e-9\nassert mean([7]) == 7\n"),
        ("capitalize_words", "Implement `capitalize_words(s)` capitalizing the first letter of each word.",
         "assert capitalize_words('hello world') == 'Hello World'\nassert capitalize_words('a b') == 'A B'\n"),
    ],
    "canary": [
        ("add", "Implement a function `add(a, b)` that returns a + b.",
         "assert add(2, 3) == 5\nassert add(-1, 1) == 0\n"),
        ("is_even", "Implement `is_even(n)` returning True iff n is even.",
         "assert is_even(4) is True\nassert is_even(3) is False\n"),
        ("reverse", "Implement `reverse(s)` returning the string reversed.",
         "assert reverse('abc') == 'cba'\nassert reverse('') == ''\n"),
    ],
}


def main() -> None:
    for split, tasks in TASKS.items():
        out = ROOT / split
        out.mkdir(parents=True, exist_ok=True)
        # remove stale files so regeneration is clean
        for old in out.glob("*.json"):
            old.unlink()
        for i, (name, prompt, tests) in enumerate(tasks, 1):
            data = {
                "id": f"{split}/{i:02d}",
                "prompt": prompt,
                "function_name": name,
                "hidden_tests": tests,
            }
            (out / f"{i:02d}.json").write_text(
                json.dumps(data, indent=2), encoding="utf-8")
    print(f"wrote {sum(len(v) for v in TASKS.values())} tasks under {ROOT}")


if __name__ == "__main__":
    main()
