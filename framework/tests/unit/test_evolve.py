"""M6 unit verification: proposals, archive, selection, operators, assembler."""

import pytest

from rsif.artifacts.model import ArtifactType
from rsif.config import RunConfig
from rsif.evolve.archive import Archive, Individual
from rsif.evolve.assembler import build_spec
from rsif.evolve.proposal import ProposalError, parse_proposal
from rsif.evolve.selection import accept_val, pass_canary, pass_screen


# -- proposal parsing ----------------------------------------------------------


def _proposal_text(**over):
    obj = {
        "surface": "skill", "operator": "skill/add",
        "hypothesis": "a helper skill speeds up string tasks",
        "rationale": "string tasks dominate failures",
        "ops": [{"op": "create", "artifact_id": "skill/strings",
                 "type": "skill",
                 "payload": {"module.py": "def main():\n    return 1\n"}}],
    }
    obj.update(over)
    import json

    return json.dumps(obj)


def test_parse_proposal_plain():
    p = parse_proposal(_proposal_text())
    assert p.surface == ArtifactType.SKILL
    assert p.operator == "skill/add"
    assert len(p.patch.ops) == 1
    assert p.patch.ops[0].artifact_id == "skill/strings"
    assert p.patch.hypothesis.startswith("a helper")


def test_parse_proposal_tolerates_fence_and_prose():
    text = "Here is my change:\n```json\n" + _proposal_text() + "\n```\nDone."
    assert parse_proposal(text).surface == ArtifactType.SKILL


def test_parse_proposal_rejects_missing_ops():
    with pytest.raises(ProposalError):
        parse_proposal(_proposal_text(ops=[]))


def test_parse_proposal_rejects_bad_surface():
    with pytest.raises(ProposalError):
        parse_proposal(_proposal_text(surface="gravity"))


def test_parse_proposal_rejects_non_json():
    with pytest.raises(ProposalError):
        parse_proposal("I think the agent should try harder.")


# -- archive ---------------------------------------------------------------------


def _ind(desc, fitness, cost=0.0, gen=1):
    return Individual(descriptor=desc, fitness=fitness, val_score=fitness,
                      spec_snapshot={"prompt/system": 1}, generation=gen,
                      cost=cost)


def test_archive_elitist_replacement():
    a = Archive()
    assert a.add(_ind(("prompt", 3), 0.5))
    assert not a.add(_ind(("prompt", 3), 0.4))  # worse: not stored
    assert a.add(_ind(("prompt", 3), 0.6))      # better: replaces
    assert len(a) == 1
    assert a.best().fitness == 0.6


def test_archive_separate_niches_and_tie_break():
    a = Archive()
    a.add(_ind(("prompt", 3), 0.5, cost=1.0))
    a.add(_ind(("skill", 2), 0.5))  # different niche: stored
    assert len(a) == 2
    # same fitness, lower cost wins the niche
    a.add(_ind(("prompt", 3), 0.5, cost=0.5))
    assert a.cells()[("prompt", 3)].cost == 0.5


def test_archive_superseded_and_history():
    a = Archive()
    a.add(_ind(("a",), 0.5))
    a.add(_ind(("b",), 0.2))
    assert a.superseded_individuals() == []  # both niches held
    a.add(_ind(("b",), 0.9))  # replaces the ("b",) incumbent
    superseded = a.superseded_individuals()
    assert [i.descriptor for i in superseded] == [("b",)]
    assert superseded[0].fitness == 0.2  # the displaced, weaker predecessor


def test_sample_parent_epsilon_reseeds_from_superseded():
    """The backtracking pressure is real: with epsilon=1 the parent is drawn
    from superseded lineages whenever any exist [2505.22954]."""
    import random

    a = Archive()
    a.add(_ind(("a",), 0.5))
    a.add(_ind(("b",), 0.2))   # first ("b",) incumbent
    a.add(_ind(("b",), 0.9))   # replaces it -> the 0.2 individual is superseded
    rng = random.Random(0)
    picks = [a.sample_parent(rng, epsilon=1.0) for _ in range(10)]
    assert {p.descriptor for p in picks} == {("b",)}
    assert {p.fitness for p in picks} == {0.2}  # superseded, not the elite
    # with no superseded material, epsilon falls through to frontier sampling
    b = Archive()
    b.add(_ind(("only",), 0.7))
    assert b.sample_parent(random.Random(0), epsilon=1.0).descriptor == ("only",)


def test_archive_frontier_sorted():
    a = Archive()
    for d, f in ((("x",), 0.1), (("y",), 0.9), (("z",), 0.5)):
        a.add(_ind(d, f))
    assert [i.fitness for i in a.frontier()] == [0.9, 0.5, 0.1]


def test_archive_persistence_roundtrip(tmp_path):
    path = tmp_path / "archive.json"
    a = Archive(path)
    a.add(_ind(("prompt", 3), 0.8))
    a.save()
    b = Archive(path)
    assert len(b) == 1
    ind = b.cells()[("prompt", 3)]
    assert ind.fitness == 0.8 and ind.spec_snapshot == {"prompt/system": 1}


def test_sample_parent_biases_to_frontier():
    import random

    a = Archive()
    a.add(_ind(("low",), 0.1))
    a.add(_ind(("high",), 0.9))
    rng = random.Random(0)
    # harmonic rank weights: the fitter elite is the likelier parent (~2/3
    # with two cells), but the weaker niche stays selectable
    picks = [a.sample_parent(rng).descriptor for _ in range(50)]
    assert picks.count(("high",)) > picks.count(("low",))
    assert set(picks) == {("high",), ("low",)}


# -- selection gates -------------------------------------------------------------


def test_pass_screen_within_epsilon():
    assert pass_screen(0.5, 0.8, 0.3)
    assert not pass_screen(0.49, 0.8, 0.3)


def test_accept_val_requires_strict_gain():
    assert accept_val(0.5, 0.4, 0.02)
    assert not accept_val(0.42, 0.4, 0.02)  # equal-ish is not a gain
    assert not accept_val(0.3, 0.4, 0.02)


def test_canary_never_regresses():
    assert pass_canary(1.0, 1.0)
    assert pass_canary(1.0, 0.9)
    assert not pass_canary(0.9, 1.0)


# -- operators -------------------------------------------------------------------


def test_load_catalog_and_validate(ws, store):
    store.seed_defaults(RunConfig())
    from rsif.evolve.operators import load_catalog, render_operators, validate_operator

    catalog = load_catalog(store)
    assert len(catalog) == 9
    assert "prompt/refine" in render_operators(catalog)
    assert validate_operator(catalog, "prompt/refine", "prompt")
    assert not validate_operator(catalog, "prompt/refine", "skill")  # mismatch
    assert not validate_operator(catalog, "prompt/nonexistent", "prompt")


# -- assembler --------------------------------------------------------------------


def test_build_spec_overlays_candidate(ws, store):
    store.seed_defaults(RunConfig())
    base = dict(store.checkout())

    spec = build_spec(store, base)
    assert "Python-solving agent" in spec.system_prompt
    assert spec.module_source  # module/default loaded
    assert spec.memory  # playbook rendered into memory

    # candidate overlay: prompt v2 without touching the active checkout
    from rsif.artifacts.model import Patch, UpdateOp
    from rsif.artifacts.store import ApplyResult

    store.apply_patch(Patch(ops=(UpdateOp(
        "prompt/system", {"system.md": "CANDIDATE PROMPT"}),)),
        proposal_id="p1")
    candidate = {**base, "prompt/system": 2}
    assert build_spec(store, candidate).system_prompt == "CANDIDATE PROMPT"
    assert build_spec(store, base).system_prompt != "CANDIDATE PROMPT"
    assert store.active_version("prompt/system") == 1  # untouched
    del ApplyResult  # imported for symmetry with engine usage


def test_build_spec_skill_manifest(ws, store):
    from rsif.artifacts.model import ArtifactType

    store.create("skill/strings", ArtifactType.SKILL, {
        "module.py": "def main(s):\n    return s.upper()\n",
        "manifest.json": '{"name": "strings", "description": "string helpers"}',
    }, proposal_id="seed")
    from rsif.artifacts.store import ApplyResult

    store.promote(ApplyResult({"skill/strings": 1}))
    spec = build_spec(store, store.snapshot())
    assert len(spec.skills) == 1
    assert spec.skills[0].name == "strings"
    assert spec.skills[0].description == "string helpers"
    assert "upper" in spec.skills[0].code
    assert "strings: string helpers" in spec.compose_system()
