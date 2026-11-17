"""The grader and what the gate does with its grades (T059, R16, FR-018), with FakeRunner."""

import asyncio
import copy
from pathlib import Path
from typing import Any

from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.models import Grade, SectionDraft, SectionMapEntry, StageRecord
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.llm.runner import FakeRunner
from thinkbible_pipeline.report.scorecard import build_scorecard
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages import registry
from thinkbible_pipeline.stages.base import Deps, run
from thinkbible_pipeline.storage import LocalBlobStore

SID = "mrk-1-1"
ENTRY = SectionMapEntry(id=SID, chapter=1, verse_start=1, verse_end=8, title="John",
                        title_source="bsb-heading")  # fmt: skip


def idea(n: int) -> dict[str, Any]:
    return {"id": f"{SID}-k{n}", "kind": "key", "title": f"Point {n}",
            "body": f"Why point {n} matters.", "sources": ["matthew-henry"],
            "quotes": [{"commentator": "matthew-henry", "text": f"Henry's words on point {n}."}],
            "agreed": False, "verseStart": 1, "verseEnd": 8, "status": "active"}  # fmt: skip


def question(n: int, targets: list[int], start: int = 1, end: int = 8) -> dict[str, Any]:
    return {"id": f"{SID}-q{n}", "type": "meaning", "verseStart": start, "verseEnd": end,
            "text": f"What do you make of detail number {n} here?",
            "targets": [f"{SID}-k{t}" for t in targets], "status": "active"}  # fmt: skip


SECTION = {
    "id": SID, "ref": "Mark 1:1-8", "chapter": 1, "verseStart": 1, "verseEnd": 8, "title": "John",
    "noPrompt": False, "context": "Mark wrote for Romans.", "viewsDiffer": None,
    "manuscriptNotes": [],
    "keyIdeas": [idea(1), idea(2), idea(3)],
    "questions": [question(1, [1, 2]), question(2, [2], 4, 4), question(3, [3], 3, 5)],
}  # fmt: skip


def setup(tmp_path: Path, make_library: Any, responses: dict[tuple[str, str], Any],
          section: dict[str, Any] | None = None, regenerated: bool = False) -> Deps:  # fmt: skip
    lib = make_library({
        ("bsb", "MRK"): {"book": "MRK", "chapters": [{"number": 1, "items": [
            {"type": "verse", "number": v, "text": f"Verse {v}."} for v in range(1, 9)]}]},
        ("kjv", "MRK"): {"book": "MRK", "chapters": [{"number": 1, "items": [
            {"type": "verse", "number": v, "text": f"Verse {v}."} for v in range(1, 9)]}]},
        ("matthew-henry", "MRK"): {"book": "MRK", "chapters": [{"number": 1, "items": [
            {"verse": 1, "verseEnd": 8, "text": "Henry's note on the passage."}]}]},
    })  # fmt: skip
    store = DraftStore("mrk", LocalBlobStore(tmp_path / "drafts"))
    store.write_section_map([ENTRY])
    draft = SectionDraft(section=copy.deepcopy(section or SECTION))
    draft.stages["generate"] = StageRecord.model_validate(
        {"promptVersion": "v3", "inputHash": "h", "completedAt": "t", "costUsd": 0.1,
         "status": "done"})  # fmt: skip
    if regenerated:
        draft.regenerated_for = "review: an earlier failure"
    store.write_draft(SID, draft)
    runner = FakeRunner(responses=responses)
    return Deps(store=store, settings=load_settings(), pricing=load_pricing(),
                runner_factory=lambda: runner, approve_estimate=lambda _s: True,
                stages=registry(), library=lib)  # fmt: skip


def grades(scores: dict[str, int]) -> dict[str, Any]:
    return {"items": [{"itemId": f"{SID}-{i}", "score": s, "reason": f"Reason for {i}.",
                       "failedRules": [] if s > 2 else ["faithful"]}
                      for i, s in scores.items()]}  # fmt: skip


ALL_GOOD = {"k1": 5, "k2": 4, "k3": 4, "q1": 4, "q2": 4, "q3": 5}


def ids(draft: SectionDraft) -> list[str]:
    return [q["id"].rsplit("-", 1)[1] for q in draft.section["questions"]]


def test_low_grades_are_dropped_and_the_rest_keep_their_order(
    tmp_path: Path, make_library: Any
) -> None:
    deps = setup(tmp_path, make_library, {("review", SID): grades({**ALL_GOOD, "q2": 2})})
    result = asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    assert result.exit_code == ExitCode.OK
    draft = deps.store.read_draft_or_new(SID)
    assert draft.grades[f"{SID}-q2"] == Grade(score=2, notes="Reason for q2. (breaks: faithful)")
    assert {d.item_id: (d.stage, d.reason) for d in draft.dropped} == {
        f"{SID}-q2": ("review", "graded 2: Reason for q2.")
    }
    assert ids(draft) == ["q1", "q3"]


def test_a_dropped_idea_takes_its_questions_and_lowers_the_question_cap(
    tmp_path: Path, make_library: Any
) -> None:
    section = {**SECTION, "questions": [question(1, [1, 2]), question(2, [2], 4, 4),
                                        question(3, [1, 3], 3, 5), question(4, [3])]}  # fmt: skip
    deps = setup(tmp_path, make_library,
                 {("review", SID): grades({**ALL_GOOD, "k3": 1, "q4": 4})}, section)  # fmt: skip
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    reasons = {d.item_id: d.reason for d in draft.dropped}
    assert reasons[f"{SID}-q4"] == "targets no key idea that was kept"
    # 2 ideas allow 2 questions: q3 (graded 5, keeps k1) and q1 (adds k2) beat q2 (k2 only).
    assert reasons[f"{SID}-q2"] == "not chosen: graded 4; better-graded questions were kept"
    assert ids(draft) == ["q1", "q3"]


def test_the_grader_picks_the_best_candidates_in_the_writers_order(
    tmp_path: Path, make_library: Any
) -> None:
    candidates = [question(1, [1]), question(2, [2]), question(3, [3]),
                  question(4, [1]), question(5, [2]), question(6, [3])]  # fmt: skip
    scores = {"k1": 5, "k2": 5, "k3": 5, "q1": 3, "q2": 5, "q3": 4, "q4": 5, "q5": 4, "q6": 2}
    deps = setup(tmp_path, make_library, {("review", SID): grades(scores)})
    draft = deps.store.read_draft_or_new(SID)
    draft.candidates = candidates
    deps.store.write_draft(SID, draft)
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    assert len(draft.grades) == 9  # every candidate is graded, not just the first three
    # One per idea first, best graded: q2 (k2), q4 (k1), q3 (k3); kept in the writer's order.
    assert ids(draft) == ["q2", "q3", "q4"]
    reasons = {d.item_id.rsplit("-", 1)[1]: d.reason for d in draft.dropped}
    assert reasons == {
        "q6": "graded 2: Reason for q6.",
        "q1": "not chosen: graded 3; better-graded questions were kept",
        "q5": "not chosen: graded 4; better-graded questions were kept",
    }
    # A re-run (a new rubric) chooses again from all six, without piling up old records.
    asyncio.run(run(RunRequest(book="mark", stages=["review"], fresh=True), deps))
    again = deps.store.read_draft_or_new(SID)
    assert ids(again) == ["q2", "q3", "q4"] and len(again.dropped) == 3


def test_pass_rates_count_grades_before_drops(tmp_path: Path, make_library: Any) -> None:
    deps = setup(tmp_path, make_library,
                 {("review", SID): grades({**ALL_GOOD, "q1": 2, "q3": 1})})  # fmt: skip
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    from datetime import UTC, datetime

    card = build_scorecard("MRK", [ENTRY], {SID: draft}, [], datetime.now(UTC))
    assert (card.ideas.passed, card.ideas.total) == (3, 3) and card.idea_pass_rate == 1.0
    assert (card.questions.passed, card.questions.total) == (1, 3)  # q1, q3 counted though dropped
    assert any("question pass rate 0.33 < 0.80" in b for b in card.blockers)


def test_a_section_left_without_a_question_is_regenerated_once_then_failed(
    tmp_path: Path, make_library: Any
) -> None:
    every_question_fails = {**ALL_GOOD, "q1": 1, "q2": 2, "q3": 1}
    deps = setup(tmp_path, make_library, {("review", SID): grades(every_question_fails)})
    result = asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    assert result.exit_code == ExitCode.SECTIONS_FAILED
    first = deps.store.read_draft_or_new(SID)
    assert first.regenerate and first.regenerate.startswith("review: ")
    assert first.failed and first.failed.endswith("(regenerates on the next run)")

    again = setup(tmp_path / "second", make_library,
                  {("review", SID): grades(every_question_fails)}, regenerated=True)  # fmt: skip
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), again))
    second = again.store.read_draft_or_new(SID)
    assert second.regenerate is None
    assert second.failed and second.failed.endswith("(after one regeneration)")


def test_the_question_spanning_most_of_the_passage_goes_first(
    tmp_path: Path, make_library: Any
) -> None:
    section = {**SECTION, "questions": [question(1, [1], 2, 2), question(2, [2], 1, 8),
                                        question(3, [3], 3, 5)]}  # fmt: skip
    deps = setup(tmp_path, make_library, {("review", SID): grades(ALL_GOOD)}, section)
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    assert ids(deps.store.read_draft_or_new(SID)) == ["q2", "q1", "q3"]


def test_the_best_big_picture_question_is_kept_and_goes_first(
    tmp_path: Path, make_library: Any
) -> None:
    """Mark 1:1-11 lost all three of its arc questions to sharper one-verse ones."""
    qs = [question(1, [1], 2, 2), question(2, [2], 4, 4), question(3, [3], 5, 5),
          question(4, [1], 1, 8)]  # fmt: skip
    section = {**SECTION, "questions": qs}
    scores = {"k1": 5, "k2": 5, "k3": 5, "q1": 5, "q2": 5, "q3": 5, "q4": 4}
    deps = setup(tmp_path, make_library, {("review", SID): grades(scores)}, section)
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    assert ids(deps.store.read_draft_or_new(SID)) == ["q4", "q2", "q3"]
    # A big-picture question graded below 4 doesn't get the place.
    weak = setup(tmp_path / "weak", make_library,
                 {("review", SID): grades({**scores, "q4": 3})}, section)  # fmt: skip
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), weak))
    assert ids(weak.store.read_draft_or_new(SID)) == ["q1", "q2", "q3"]


def test_the_notes_are_graded_too(tmp_path: Path, make_library: Any) -> None:
    section = {**SECTION, "viewsDiffer": "Clarke reads this differently from Henry."}
    scores = {**ALL_GOOD, "views": 2, "context": 4}
    deps = setup(tmp_path, make_library, {("review", SID): grades(scores)}, section)
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    assert draft.section["viewsDiffer"] is None  # a weak views-differ note is removed
    assert [(d.item_id, d.reason) for d in draft.dropped] == [
        (f"{SID}-views", "graded 2: Reason for views.")
    ]
    # A weak context note can't be removed, so the section is regenerated once.
    weak = setup(tmp_path / "weak", make_library,
                 {("review", SID): grades({**ALL_GOOD, "context": 1})})  # fmt: skip
    result = asyncio.run(run(RunRequest(book="mark", stages=["review"]), weak))
    assert result.exit_code == ExitCode.SECTIONS_FAILED
    failed = weak.store.read_draft_or_new(SID)
    assert failed.regenerate == "review: the context note graded 1: Reason for context."


def test_a_section_left_without_a_key_idea_is_flagged(tmp_path: Path, make_library: Any) -> None:
    every_idea_fails = {**ALL_GOOD, "k1": 1, "k2": 2, "k3": 1}
    deps = setup(tmp_path, make_library, {("review", SID): grades(every_idea_fails)})
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    assert draft.section["keyIdeas"] == [] and draft.regenerate is not None
