"""The grader and the level check (T059, R11, R16, FR-018) with FakeRunner: no model calls."""

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
    return {"id": f"{SID}-k{n}", "title": f"Point {n}", "body": f"Why point {n} matters.",
            "sources": ["matthew-henry"], "agreed": False, "verseStart": 1, "verseEnd": 8,
            "status": "active"}  # fmt: skip


def question(n: int, level: int, alt: bool, targets: list[int], start: int = 1, end: int = 8,
             ) -> dict[str, Any]:  # fmt: skip
    return {"id": f"{SID}-q{n}", "level": level, "type": "meaning", "verseStart": start,
            "verseEnd": end, "text": f"What do you make of detail number {n} here?",
            "targets": [f"{SID}-k{t}" for t in targets], "isAlternate": alt,
            "status": "active"}  # fmt: skip


SECTION = {
    "id": SID, "ref": "Mark 1:1-8", "chapter": 1, "verseStart": 1, "verseEnd": 8, "title": "John",
    "noPrompt": False, "context": "Mark wrote for Romans.", "viewsDiffer": None,
    "manuscriptNotes": [],
    "keyIdeas": [idea(1), idea(2), idea(3)],
    "questions": [
        question(1, 1, False, [1], 2, 2), question(2, 1, True, [2], 4, 4),
        question(3, 2, False, [1, 2]), question(4, 3, False, [3]), question(5, 3, True, [1], 3, 5),
    ],
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


ALL_GOOD = {"k1": 5, "k2": 4, "k3": 4, "q1": 4, "q2": 4, "q3": 5, "q4": 4, "q5": 4}


def test_low_grades_are_dropped_and_an_alternate_takes_the_primarys_place(
    tmp_path: Path, make_library: Any
) -> None:
    deps = setup(tmp_path, make_library,
                 {("review", SID): grades({**ALL_GOOD, "q1": 2, "q5": 1})})  # fmt: skip
    result = asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    assert result.exit_code == ExitCode.OK
    draft = deps.store.read_draft_or_new(SID)
    assert draft.grades[f"{SID}-q1"] == Grade(score=2, notes="Reason for q1. (breaks: faithful)")
    dropped = {d.item_id: (d.stage, d.reason) for d in draft.dropped}
    assert dropped == {f"{SID}-q1": ("review", "graded 2: Reason for q1."),
                       f"{SID}-q5": ("review", "graded 1: Reason for q5.")}  # fmt: skip
    pool = [
        (q["id"].rsplit("-", 1)[1], q["level"], q["isAlternate"])
        for q in draft.section["questions"]
    ]
    assert pool == [("q2", 1, False), ("q3", 2, False), ("q4", 3, False)]  # q2 stepped up


def test_a_dropped_idea_takes_its_questions_and_lowers_the_level_cap(
    tmp_path: Path, make_library: Any
) -> None:
    deps = setup(tmp_path, make_library, {("review", SID): grades({**ALL_GOOD, "k3": 1})})
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    reasons = {d.item_id: d.reason for d in draft.dropped}
    assert reasons[f"{SID}-q4"] == "targets no key idea that was kept"
    assert reasons[f"{SID}-q5"].startswith("Level 3 needs at least 3 key ideas")
    assert {q["level"] for q in draft.section["questions"]} == {1, 2}


def test_pass_rates_count_grades_before_drops(tmp_path: Path, make_library: Any) -> None:
    deps = setup(tmp_path, make_library,
                 {("review", SID): grades({**ALL_GOOD, "q1": 2, "q5": 1})})  # fmt: skip
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    from datetime import UTC, datetime

    card = build_scorecard("MRK", [ENTRY], {SID: draft}, [], datetime.now(UTC))
    assert (card.ideas.passed, card.ideas.total) == (3, 3) and card.idea_pass_rate == 1.0
    assert (card.questions.passed, card.questions.total) == (3, 5)  # q1, q5 counted though dropped
    assert card.question_pass_rate == 0.6
    assert any("question pass rate 0.60 < 0.80" in b for b in card.blockers)


def levels_responses(covered: dict[str, list[int]]) -> dict[tuple[str, str], Any]:
    qs = [f"q{n}" for n in range(1, 6)]
    return {
        ("levels.answer", SID): {"answers": [{"questionId": f"{SID}-{q}", "answer": "An answer."}
                                             for q in qs]},
        ("levels.judge", SID): {"judgments": [
            {"questionId": f"{SID}-{q}",
             "coveredTargetIds": [f"{SID}-k{t}" for t in covered.get(q, [])]}
            for q in qs]},
    }  # fmt: skip


def test_level_check_moves_an_easy_level_3_and_drops_a_hard_level_1(
    tmp_path: Path, make_library: Any
) -> None:
    covered = {"q1": [], "q2": [2], "q3": [1], "q4": [], "q5": [1]}  # q5 (L3, one target) reached
    deps = setup(tmp_path, make_library, levels_responses(covered))
    result = asyncio.run(run(RunRequest(book="mark", stages=["levels"]), deps))
    assert result.exit_code == ExitCode.OK
    draft = deps.store.read_draft_or_new(SID)
    assert [(c.question_id, c.from_level, c.to_level) for c in draft.level_changes] == [
        (f"{SID}-q5", 3, 2)
    ]
    assert [(d.item_id, d.stage) for d in draft.dropped] == [(f"{SID}-q1", "levels")]
    pool = [
        (q["id"].rsplit("-", 1)[1], q["level"], q["isAlternate"])
        for q in draft.section["questions"]
    ]
    assert pool == [("q2", 1, False), ("q3", 2, False), ("q5", 2, True), ("q4", 3, False)]


def test_a_section_left_without_a_level_is_regenerated_once_then_failed(
    tmp_path: Path, make_library: Any
) -> None:
    covered = {"q1": [1], "q2": [2], "q3": [1], "q4": [3], "q5": [1]}  # both Level 3s too easy
    deps = setup(tmp_path, make_library, levels_responses(covered))
    result = asyncio.run(run(RunRequest(book="mark", stages=["levels"]), deps))
    assert result.exit_code == ExitCode.SECTIONS_FAILED
    first = deps.store.read_draft_or_new(SID)
    assert first.regenerate and first.regenerate.startswith("levels: ")
    assert first.failed and first.failed.endswith("(regenerates on the next run)")

    again = setup(tmp_path / "second", make_library, levels_responses(covered), regenerated=True)
    asyncio.run(run(RunRequest(book="mark", stages=["levels"]), again))
    second = again.store.read_draft_or_new(SID)
    assert second.regenerate is None
    assert second.failed and second.failed.endswith("(after one regeneration)")


def test_a_section_left_without_a_key_idea_is_flagged(tmp_path: Path, make_library: Any) -> None:
    every_idea_fails = {**ALL_GOOD, "k1": 1, "k2": 2, "k3": 1}
    deps = setup(tmp_path, make_library, {("review", SID): grades(every_idea_fails)})
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    assert draft.section["keyIdeas"] == [] and draft.regenerate is not None
