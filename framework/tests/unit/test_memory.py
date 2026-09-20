"""M5 verification: retrieval, reflections, insights, playbook."""

import pytest

from rsif.memory.episodic import ReflectionStore
from rsif.memory.insights import InsightStore
from rsif.memory.playbook import PlaybookEditor, PlaybookError, Section, parse_playbook
from rsif.memory.retrieve import TfidfRetriever


def test_tfidf_ranks_relevant_doc_first():
    r = TfidfRetriever()
    docs = [
        "baking a chocolate cake recipe",
        "a completely unrelated weather report",
        "binary search on sorted arrays and trees",
    ]
    ranked = r.retrieve("binary search", docs)
    assert ranked[0][0] == 2  # the binary-search doc ranks first
    assert ranked[0][1] > 0.0


def test_stemming_unifies_inflections():
    from rsif.memory.retrieve import tokenize

    assert "sort" in tokenize("sorting sorted sorters")


def test_tfidf_excludes_irrelevant_docs():
    r = TfidfRetriever()
    docs = ["chocolate cake", "binary search on sorted arrays"]
    ranked = r.retrieve("binary search", docs)
    assert [i for i, _ in ranked] == [1]


def test_tfidf_empty_docs():
    assert TfidfRetriever().retrieve("q", []) == []


def test_reflection_retrieved_for_similar_task(tmp_path):
    store = ReflectionStore(tmp_path / "r.jsonl", clock=lambda: 0.0)
    store.add("task/sort", "use the sorted() builtin and check edge cases")
    store.add("task/cake", "preheat the oven first")
    hits = store.retrieve("sorting a list of numbers")
    assert hits and "sorted" in hits[0].text


def test_reflection_not_retrieved_for_dissimilar(tmp_path):
    store = ReflectionStore(tmp_path / "r.jsonl", clock=lambda: 0.0)
    store.add("task/cake", "preheat the oven first")
    hits = store.retrieve("sorting a list of numbers")
    assert hits == []


def test_reflection_persistence(tmp_path):
    store = ReflectionStore(tmp_path / "r.jsonl", clock=lambda: 0.0)
    store.add("t1", "reflection one")
    store2 = ReflectionStore(tmp_path / "r.jsonl", clock=lambda: 0.0)
    assert len(store2) == 1
    assert store2.all()[0].text == "reflection one"


def test_insight_distill_and_retire(tmp_path):
    store = InsightStore(tmp_path / "i.jsonl", clock=lambda: 0.0)
    store.distill([("traj1", "always verify with hidden tests"),
                   ("traj2", "prefer iterative solutions")])
    assert len(store) == 2
    # mark both as correlated with failure, retire
    store.record_failure([0, 1])
    store.record_failure([0, 1])
    retired = store.retire_correlated(threshold=2)
    assert len(retired) == 2 and len(store) == 0


def test_insight_retrieval_increments_uses(tmp_path):
    store = InsightStore(tmp_path / "i.jsonl", clock=lambda: 0.0)
    store.distill([("t", "use a loop not recursion")])
    store.retrieve("loops and iteration")
    assert store.all()[0].uses == 1


def test_playbook_bounded_ops(tmp_path):
    editor = PlaybookEditor(max_sections=5, max_ops_per_patch=2)
    sections = [Section("s1", "General", "read carefully")]
    ops = [
        {"op": "add", "section": {"id": "s2", "title": "Edge cases",
                                  "body": "test empty input"}},
        {"op": "update", "id": "s1", "body": "read very carefully"},
    ]
    new = editor.apply(sections, ops)
    assert [s.id for s in new] == ["s1", "s2"]
    assert new[0].body == "read very carefully"


def test_playbook_rejects_unbounded_patch():
    editor = PlaybookEditor(max_ops_per_patch=2)
    sections = [Section("s1", "a", "b")]
    ops = [{"op": "add", "section": {"id": f"s{i}", "title": "t", "body": "b"}}
           for i in range(3)]
    with pytest.raises(PlaybookError):
        editor.apply(sections, ops)


def test_playbook_rejects_overflow():
    editor = PlaybookEditor(max_sections=1)
    sections = [Section("s1", "a", "b")]
    ops = [{"op": "add", "section": {"id": "s2", "title": "t", "body": "b"}}]
    with pytest.raises(PlaybookError):
        editor.apply(sections, ops)


def test_playbook_parse_roundtrip():
    from rsif.memory.playbook import serialize_playbook

    sections = [Section("s1", "T", "b")]
    assert parse_playbook(serialize_playbook(sections)) == sections
