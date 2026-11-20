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
from thinkbible_pipeline.report.render import _central_note
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
          section: dict[str, Any] | None = None, regenerated: bool = False,
          central: str | None = None) -> Deps:  # fmt: skip
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
    draft = SectionDraft(section=copy.deepcopy(section or SECTION), central_idea=central)
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
    deps = setup(tmp_path, make_library, {("review", SID): grades({**ALL_GOOD, "q2": 2})},
                 central=f"{SID}-k1")  # q1 is a 4 on the central k1; q3 is a 5  # fmt: skip
    result = asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    assert result.exit_code == ExitCode.OK
    draft = deps.store.read_draft_or_new(SID)
    assert draft.grades[f"{SID}-q2"] == Grade(score=2, notes="Reason for q2. (breaks: faithful)")
    assert {d.item_id: (d.stage, d.reason) for d in draft.dropped} == {
        f"{SID}-q2": ("review", "graded 2: Reason for q2.")
    }
    assert ids(draft) == ["q3", "q1"]  # no big-picture question: the 5 leads


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
    # No central idea here, so the best-graded, q3, goes first.
    assert reasons[f"{SID}-q2"] == "not chosen: graded 4; better-graded questions were kept"
    assert ids(draft) == ["q3", "q1"]


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
    # The candidates' pass rate is information; what blocks is what readers get. q2 (a 4) leads,
    # but three ideas allow three questions and only one is left.
    assert not any("pass rate" in b and "question" in b for b in card.blockers)
    assert (card.strong_first.passed, card.strong_first.total) == (1, 1)
    assert (card.full_sets.passed, card.full_sets.total) == (0, 1)
    assert any("sections with a full set of questions: 0.00 < 0.95" in b for b in card.blockers)


def test_a_weak_first_question_blocks_promotion(tmp_path: Path, make_library: Any) -> None:
    deps = setup(tmp_path, make_library,
                 {("review", SID): grades({**ALL_GOOD, "q1": 3, "q2": 3, "q3": 3})})  # fmt: skip
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    from datetime import UTC, datetime

    card = build_scorecard("MRK", [ENTRY], {SID: deps.store.read_draft_or_new(SID)}, [],
                           datetime.now(UTC))  # fmt: skip
    assert card.full_set_rate == 1.0 and card.strong_first_rate == 0.0
    assert any("first questions graded 4 or 5: 0.00 < 0.90" in b for b in card.blockers)


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


def test_with_no_central_question_the_best_graded_goes_first_ties_to_the_widest(
    tmp_path: Path, make_library: Any
) -> None:
    section = {**SECTION, "questions": [question(1, [1], 2, 2), question(2, [2], 1, 8),
                                        question(3, [3], 3, 5)]}  # fmt: skip
    deps = setup(tmp_path, make_library, {("review", SID): grades(ALL_GOOD)}, section)
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    assert ids(deps.store.read_draft_or_new(SID)) == ["q3", "q1", "q2"]  # q3 is the only 5
    tied = {**ALL_GOOD, "q3": 4}
    deps = setup(tmp_path / "tied", make_library, {("review", SID): grades(tied)}, section)
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    assert ids(deps.store.read_draft_or_new(SID)) == ["q2", "q1", "q3"]  # all 4s: the widest


def test_a_place_is_kept_for_the_central_idea_and_the_best_graded_leads(
    tmp_path: Path, make_library: Any
) -> None:
    """A question on the central idea graded 4 or more is kept (2026-11-18); without a big-picture
    question, the best-graded leads (2026-11-19)."""
    qs = [question(1, [1], 2, 2), question(2, [2], 4, 4), question(3, [3], 3, 5),
          question(4, [2], 1, 8)]  # fmt: skip
    scores = {"k1": 5, "k2": 5, "k3": 5, "q1": 5, "q2": 4, "q3": 5, "q4": 4}
    deps = setup(tmp_path, make_library, {("review", SID): grades(scores)},
                 {**SECTION, "questions": qs}, central=f"{SID}-k2")  # fmt: skip
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    # q2 and q4 tie at 4 on the central k2: the whole-passage q4 is kept; the 5s fill the rest,
    # and the wider 5 (q3) leads.
    assert ids(draft) == ["q3", "q1", "q4"]
    note = _central_note(draft, [i["id"] for i in draft.section["keyIdeas"]],
                         draft.section["questions"])  # fmt: skip
    assert note and note.startswith("Question 1 is about another idea")


def test_without_a_strong_central_question_the_best_graded_leads(
    tmp_path: Path, make_library: Any
) -> None:
    qs = [question(1, [1], 2, 2), question(2, [2], 4, 4), question(3, [3], 3, 5)]
    scores = {"k1": 5, "k2": 5, "k3": 5, "q1": 5, "q2": 3, "q3": 5}
    deps = setup(tmp_path, make_library, {("review", SID): grades(scores)},
                 {**SECTION, "questions": qs}, central=f"{SID}-k2")  # fmt: skip
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    assert ids(draft) == ["q3", "q1", "q2"]
    note = _central_note(draft, [i["id"] for i in draft.section["keyIdeas"]],
                         draft.section["questions"])  # fmt: skip
    assert note and note.startswith("Question 1 is about another idea")


def test_a_lower_grade_never_beats_a_higher_one(tmp_path: Path, make_library: Any) -> None:
    """Regression (Mark 1:21-28): covering every idea first kept a 3 over a 5, and a reserved
    place for a whole-passage question let a broad 4 beat a sharp 5."""
    qs = [question(1, [1], 2, 2), question(2, [2], 4, 4), question(3, [3], 5, 5),
          question(4, [1], 3, 3), question(5, [2], 1, 8)]  # fmt: skip
    section = {**SECTION, "questions": qs}
    scores = {"k1": 5, "k2": 5, "k3": 5, "q1": 5, "q2": 5, "q3": 3, "q4": 5, "q5": 4}
    deps = setup(tmp_path, make_library, {("review", SID): grades(scores)}, section)
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    # Three 5s are kept, though q4 repeats q1's idea and neither q3 (k3, a 3) nor q5 (the whole
    # passage, a 4) made it.
    assert ids(deps.store.read_draft_or_new(SID)) == ["q1", "q2", "q4"]


def test_ties_go_to_a_new_idea_then_to_the_whole_passage(tmp_path: Path, make_library: Any) -> None:
    qs = [question(1, [1], 2, 2), question(2, [2], 4, 4), question(3, [3], 5, 5),
          question(4, [1], 1, 8)]  # fmt: skip
    section = {**SECTION, "questions": qs}
    scores = {"k1": 5, "k2": 5, "k3": 5, "q1": 5, "q2": 5, "q3": 5, "q4": 5}
    deps = setup(tmp_path, make_library, {("review", SID): grades(scores)}, section)
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    # All 5s: the whole-passage q4 wins the tie on k1 over q1, then q2 and q3 add k2 and k3;
    # q4 spans the most, so it goes first.
    assert ids(deps.store.read_draft_or_new(SID)) == ["q4", "q2", "q3"]


def test_equal_questions_go_to_the_better_graded_idea(tmp_path: Path, make_library: Any) -> None:
    """Mark 1:1-11 (2026-11-19): a 4 on an idea graded 3 had beaten a 4 on an idea graded 5."""
    qs = [question(1, [1], 1, 8), question(2, [2], 2, 2), question(3, [3], 3, 3),
          question(4, [4], 4, 4)]  # fmt: skip
    section = {**SECTION, "keyIdeas": [idea(1), idea(2), idea(3), idea(4)], "questions": qs}
    scores = {"k1": 4, "k2": 3, "k3": 5, "k4": 4, "q1": 5, "q2": 4, "q3": 4, "q4": 4}
    deps = setup(tmp_path, make_library, {("review", SID): grades(scores)}, section,
                 central=f"{SID}-k1")  # fmt: skip
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    # Three places: q1 opens (the central k1); q2, q3, q4 tie at 4 on new ideas, and the ideas
    # graded 5 and 4 beat the one graded 3, though the writer put q2 first.
    assert ids(deps.store.read_draft_or_new(SID)) == ["q1", "q3", "q4"]


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


def test_a_big_picture_question_graded_4_or_more_goes_first(
    tmp_path: Path, make_library: Any
) -> None:
    """Mark 1:16-20 (2026-11-19): the grader's focus mark decides which kept question leads."""
    qs = [question(1, [1], 1, 8), question(2, [2], 4, 4), question(3, [3], 3, 5)]
    scores = {"k1": 5, "k2": 5, "k3": 5, "q1": 5, "q2": 4, "q3": 5}

    def graded(focus: dict[str, str]) -> dict[str, Any]:
        out = grades(scores)
        for item in out["items"]:
            name = item["itemId"].removeprefix(f"{SID}-")
            if name in focus:
                item["focus"] = focus[name]
        return out

    def order(focus: dict[str, str], name: str) -> list[str]:
        deps = setup(tmp_path / name, make_library, {("review", SID): graded(focus)},
                     {**SECTION, "questions": qs}, central=f"{SID}-k2")  # fmt: skip
        asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
        draft = deps.store.read_draft_or_new(SID)
        assert draft.grades[f"{SID}-q1"].focus == focus.get("q1")
        return ids(draft)

    # The central q2 (a 4, a detail) would open; the big-picture q1 (a 5) leads instead.
    assert order({"q1": "big-picture", "q2": "detail", "q3": "detail"}, "big") == ["q1", "q2", "q3"]
    # With no big-picture question, the best-graded leads (Mark 3:1-6): the 5s outrank the central
    # 4, and the wider of them (q1) goes first.
    assert order({"q1": "detail", "q2": "detail", "q3": "detail"}, "none") == ["q1", "q2", "q3"]


def test_equal_grades_keep_the_big_picture_question(tmp_path: Path, make_library: Any) -> None:
    """Mark 3:1-6 (2026-11-19): big-picture questions had lost ties to details on writer's order."""
    qs = [question(1, [1], 3, 3), question(2, [1], 4, 4), question(3, [2], 5, 5),
          question(4, [3], 6, 6), question(5, [3], 6, 6)]  # fmt: skip
    scores = {"k1": 5, "k2": 5, "k3": 5, "q1": 4, "q2": 4, "q3": 5, "q4": 5, "q5": 5}
    out = grades(scores)
    for item in out["items"]:
        if item["itemId"].endswith(("-q2", "-q5")):
            item["focus"] = "big-picture"
        elif "-q" in item["itemId"]:
            item["focus"] = "detail"
    deps = setup(tmp_path, make_library, {("review", SID): out},
                 {**SECTION, "questions": qs}, central=f"{SID}-k1")  # fmt: skip
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    # The central place goes to big-picture q2 over q1 (both 4s); of the 5s, big-picture q5 beats
    # q4 for k3, and q3 adds k2. The big-picture 5 leads.
    assert ids(deps.store.read_draft_or_new(SID)) == ["q5", "q2", "q3"]


def test_a_selection_change_reuses_the_stored_grades(tmp_path: Path, make_library: Any) -> None:
    """Re-running review with the same grader re-selects from the stored grades: no model call."""
    deps = setup(tmp_path, make_library, {("review", SID): grades(ALL_GOOD)})
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    first = deps.store.read_draft_or_new(SID)
    runner = deps.runner
    calls = len(runner.calls)
    runner.responses.clear()  # any model call would now fail
    result = asyncio.run(run(RunRequest(book="mark", stages=["review"], fresh=True), deps))
    assert result.exit_code == ExitCode.OK and len(runner.calls) == calls
    again = deps.store.read_draft_or_new(SID)
    assert again.grades == first.grades and ids(again) == ids(first)


def test_the_estimate_counts_reused_grades_at_no_cost(tmp_path: Path, make_library: Any) -> None:
    from thinkbible_pipeline.stages.base import MIN_DEFAULT_CAP_USD, estimate_run

    deps = setup(tmp_path, make_library, {("review", SID): grades(ALL_GOOD)})
    asyncio.run(run(RunRequest(book="mark", stages=["review"]), deps))
    plans, summary = estimate_run(RunRequest(book="mark", stages=["review"], fresh=True), deps)
    assert (len(plans[0].items), plans[0].free, plans[0].estimate_usd) == (1, 1, 0.0)
    assert not summary.calls_model  # nothing to approve: no model call is expected
    assert summary.cap_usd == MIN_DEFAULT_CAP_USD  # but a cap stays, in case one is made
