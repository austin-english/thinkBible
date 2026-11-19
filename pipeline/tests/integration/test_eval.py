"""``eval`` (T083, FR-029) on the fixture book with the scripted runner: no model calls.

Checks that the current arm is reused for free when it matches the settings, that a candidate
runs in a scratch store and never touches the real drafts, and that the comparison and the page
are built from both arms.
"""

import asyncio
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from thinkbible_pipeline.drafts.models import Grade, SectionDraft
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.evals import report
from thinkbible_pipeline.evals.run import (
    Arm,
    EvalError,
    candidate_settings,
    load_candidate,
    load_sample,
    plan_eval,
    run_eval,
)
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages import expand_all
from thinkbible_pipeline.stages.base import Deps, run

# The fixture book and its scripted runner, shared with the end-to-end test (no model calls).
_spec = importlib.util.spec_from_file_location(
    "fixture_book", Path(__file__).with_name("test_generate_fixture_book.py")
)
assert _spec and _spec.loader
_fixture_book = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture_book)
ScriptedRunner, make = _fixture_book.ScriptedRunner, _fixture_book.make


def files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def generated(tmp_path: Path, make_library: Any) -> tuple[Deps, ScriptedRunner, list[str]]:
    deps, runner = make(tmp_path, make_library)
    request = RunRequest(book="mark", stages=expand_all("all"))  # type: ignore[arg-type]
    asyncio.run(run(request, deps))
    ids = deps.store.section_ids()
    return deps, runner, ids[1:3]  # not the first, so the previous section's summary is needed


def write_sample(root: Path, sections: list[str], overlay: str = "") -> None:
    (root / "candidates").mkdir(parents=True)
    (root / "s.json").write_text(json.dumps({"book": "mark", "sections": sections}))
    (root / "candidates" / "c.toml").write_text(overlay)


def test_a_candidate_runs_in_scratch_and_never_touches_the_real_drafts(
    generated: tuple[Deps, ScriptedRunner, list[str]], tmp_path: Path
) -> None:
    deps, runner, sections = generated
    write_sample(tmp_path / "evals", sections)
    sample = load_sample("s", tmp_path / "evals")
    cand = candidate_settings(load_candidate("c", tmp_path / "evals"))
    plan = plan_eval(deps.store, sample, deps.settings, cand, repeats=2)
    assert plan.current is not None and plan.stale == []  # same versions: reused for free
    assert plan.labels == ["candidate 1", "candidate 2"]
    assert plan.cost_usd > 0

    real_before = files(tmp_path / "drafts")
    calls_before = len(runner.calls)

    def deps_for(store: DraftStore, settings: Any) -> Deps:
        return Deps(store=store, settings=settings, pricing=deps.pricing,
                    runner_factory=lambda: runner,  # type: ignore[arg-type,return-value]
                    approve_estimate=lambda _s: True, stages=deps.stages,
                    library=deps.library)  # fmt: skip

    base, runs = asyncio.run(
        run_eval(plan, deps.store, tmp_path / "out", current=deps.settings, candidate=cand,
                 deps_for=deps_for)
    )  # fmt: skip
    assert files(tmp_path / "drafts") == real_before  # the real drafts are only read
    # Two runs of extract, questions and review for each sample section; no summaries.
    assert len(runner.calls) - calls_before == 2 * 3 * len(sections)
    assert [r.label for r in runs] == ["candidate 1", "candidate 2"]
    for arm in runs:
        assert sorted(arm.drafts) == sorted(sections) and not arm.failures
        assert all(d.stages["review"].status == "done" for d in arm.drafts.values())
    assert (tmp_path / "out" / "candidate-1").is_dir()

    threshold = deps.settings.review_flag_threshold
    base_m = report.measure(base, threshold)
    cand_m = report.averaged([report.measure(r, threshold) for r in runs])
    verdict = report.compare(base_m, cand_m)
    assert verdict.adopt  # the scripted writer answers the same way every time
    assert base_m.sections == cand_m.sections == len(sections)
    page = report.render("s", "c", sections, [base, *runs], base_m, cand_m, verdict)
    assert all(sid in page for sid in sections) and "candidate 2" in page


def test_fresh_current_generates_the_current_arm_too(
    generated: tuple[Deps, ScriptedRunner, list[str]], tmp_path: Path
) -> None:
    deps, _runner, sections = generated
    write_sample(tmp_path / "evals", sections)
    sample = load_sample("s", tmp_path / "evals")
    plan = plan_eval(deps.store, sample, deps.settings, deps.settings, fresh_current=True)
    assert plan.current is None and plan.labels == ["current", "candidate"]


def test_a_changed_writer_prompt_makes_the_current_drafts_stale(
    generated: tuple[Deps, ScriptedRunner, list[str]], tmp_path: Path
) -> None:
    deps, _runner, sections = generated
    write_sample(tmp_path / "evals", sections)
    sample = load_sample("s", tmp_path / "evals")
    older = candidate_settings({"prompts": {"question_guide": "v4"}})
    plan = plan_eval(deps.store, sample, older, deps.settings)
    assert plan.current is None and plan.stale == sections and plan.labels[0] == "current"


def test_a_candidate_may_not_change_the_grader(tmp_path: Path) -> None:
    write_sample(tmp_path, ["mrk-1-1"], '[stages.review]\nmodel = "x"\n')
    with pytest.raises(EvalError, match="calibrate"):
        load_candidate("c", tmp_path)
    with pytest.raises(EvalError, match="no sample"):
        load_sample("missing", tmp_path)


def _arm(first: int, focus: str, notes: str = "") -> Arm:
    draft = SectionDraft(section={
        "keyIdeas": [{"id": "s-k1", "kind": "key", "title": "T"}],
        "questions": [{"id": "s-q1", "text": "Why?", "targets": ["s-k1"]}],
    })  # fmt: skip
    draft.grades = {"s-q1": Grade(score=first, notes=notes, focus=focus),  # type: ignore[arg-type]
                    "s-k1": Grade(score=5, notes="")}  # fmt: skip
    return Arm("a", {"s": draft})


def test_a_worse_first_question_keeps_the_current_prompts() -> None:
    current = report.measure(_arm(5, "big-picture"), threshold=2)
    worse = report.measure(_arm(3, "detail", "Thin (breaks: answerable, open)"), threshold=2)
    assert (current.strong_first, current.big_first, worse.strong_first) == (1.0, 1.0, 0.0)
    assert worse.broken == {"answerable": 1, "open": 1}
    verdict = report.compare(current, worse)
    assert not verdict.adopt
    assert [label for label, *_, ok in verdict.rows if not ok] == [
        "First questions graded 4-5", "Big-picture first questions",
        "Mean grade of kept questions",
    ]  # fmt: skip
