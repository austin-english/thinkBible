"""The quality gate's rule checks (T058, FR-016): each seeded defect is dropped with a reason."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.models import Evidence, SectionDraft, SectionMapEntry, StageRecord
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.gate.checks import (
    CheckContext,
    idea_problem,
    is_yes_no,
    question_problem,
    repeats_idea,
)
from thinkbible_pipeline.llm.runner import FakeRunner
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages import registry
from thinkbible_pipeline.stages.base import Deps, run
from thinkbible_pipeline.stages.checks import apply_checks
from thinkbible_pipeline.storage import LocalBlobStore

SID = "mrk-7-14"
# Mark 7: the KJV has verse 16, the BSB doesn't.
CTX = CheckContext(
    verse_sets={
        "bsb": {(7, v) for v in range(1, 38) if v != 16},
        "kjv": {(7, v) for v in range(1, 38)},
    }
)
IDEAS = [("What defiles comes from within", "Jesus teaches that evil thoughts come out of the "
          "heart, and those are what make a person unclean before God.")]  # fmt: skip


@pytest.mark.parametrize(
    ("title", "body", "reason"),
    [
        ("T" * 61, "Fine.", "title length 61"),
        ("Title", "B" * 239 + ".!", "body length 241"),
        ("Title", "Jesus says ", "incomplete text"),
        ("Henry on purity", "Purity starts inside.", "names a commentator (Henry)"),
        ("Title", "As Clarke notes, purity starts inside.", "names a commentator (Clarke)"),
        ("Title", "See {{ref:7:16}} for this.", "doesn't resolve in BSB"),
        ("Title", "See {{ref:7}} here.", "malformed verse placeholder"),
    ],
)
def test_idea_defects(title: str, body: str, reason: str) -> None:
    problem = idea_problem(title, body, CTX)
    assert problem is not None and reason in problem


def test_good_idea_passes() -> None:
    assert (
        idea_problem("What comes from within", "Jesus moves purity inside {{ref:7:15}}.", CTX)
        is None
    )


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("Why might Jesus say this", "ending with '?'"),
        ("Why?", "question length 4"),
        ("Why " + "x" * 200 + "?", "question length 205"),
        ("Jesus speaks about food. Is that important?", "yes/no question"),
        ("Does this matter to you?", "yes/no question"),
        ("Why might Henry think this matters?", "names a commentator (Henry)"),
        ("Why might what defiles comes from within matter here?", "gives away a key idea"),
        ("Jesus says evil thoughts come out of the heart, and those are what make a person "
         "unclean. Why?", "gives away a key idea"),
        ("What does {{ref:7:16}} add here?", "doesn't resolve in BSB"),
    ],
)  # fmt: skip
def test_question_defects(text: str, reason: str) -> None:
    problem = question_problem(text, IDEAS, CTX)
    assert problem is not None and reason in problem, problem


def test_open_questions_pass() -> None:
    for text in [
        "Jesus turns from food to the heart. What do you make of that shift?",
        "Did the disciples understand why Jesus said this?",  # has an open "why"
        "How might this change the way you think about being clean?",
    ]:
        assert question_problem(text, IDEAS, CTX) is None, text
    assert is_yes_no("Is it wrong to eat with unwashed hands?")
    assert repeats_idea("What comes to mind?", IDEAS) is None


def section(**overrides: Any) -> dict[str, Any]:
    ideas = [
        {"id": f"{SID}-k1", "title": "What defiles comes from within", "body": "Purity begins in "
         "the heart.", "sources": ["matthew-henry", "adam-clarke"], "agreed": True,
         "verseStart": 14, "verseEnd": 23, "status": "active"},
        {"id": f"{SID}-k2", "title": "Food passes through", "body": "Food can't make a person "
         "unclean.", "sources": ["matthew-henry"], "agreed": False, "verseStart": 18,
         "verseEnd": 19, "status": "active"},
    ]  # fmt: skip
    questions = [
        {"id": f"{SID}-q1", "type": "meaning", "verseStart": 14, "verseEnd": 23,
         "text": "What is Jesus saying about being clean in this passage?",
         "targets": [f"{SID}-k1", f"{SID}-k2"], "status": "active"},
        {"id": f"{SID}-q2", "type": "noticing", "verseStart": 19, "verseEnd": 19,
         "text": "Why might Jesus mention where food goes?", "targets": [f"{SID}-k2"],
         "status": "active"},
    ]  # fmt: skip
    doc = {"id": SID, "ref": "Mark 7:14-23", "chapter": 7, "verseStart": 14, "verseEnd": 23,
           "title": "What Defiles a Man", "noPrompt": False, "context": "Mark wrote for Romans.",
           "viewsDiffer": None, "manuscriptNotes": [], "keyIdeas": ideas,
           "questions": questions}  # fmt: skip
    doc.update(overrides)
    return doc


def draft(doc: dict[str, Any]) -> SectionDraft:
    return SectionDraft(
        section=doc,
        evidence={
            f"{SID}-k1": [Evidence(commentator="matthew-henry", quote="q"),
                          Evidence(commentator="adam-clarke", quote="q")],
            f"{SID}-k2": [Evidence(commentator="matthew-henry", quote="q")],
        },
    )  # fmt: skip


def test_a_clean_section_passes_the_schema_and_cross_field_rules() -> None:
    d = draft(section())
    assert apply_checks(d, CTX) == [] and d.dropped == []


def test_an_unbacked_source_takes_its_idea_and_the_questions_that_need_it() -> None:
    d = draft(section())
    d.evidence[f"{SID}-k2"] = []  # Henry's quote for k2 was never verified
    problems = apply_checks(d, CTX)
    assert [(x.item_id, x.stage) for x in d.dropped][:1] == [(f"{SID}-k2", "check")]
    assert d.dropped[0].reason.startswith("evidence:")
    # q2 targeted only k2: dropped. q1 keeps k1, and one idea allows one question.
    dropped = {x.item_id: x.reason for x in d.dropped}
    assert dropped[f"{SID}-q2"] == "targets no key idea that was kept"
    assert [(q["id"], q["targets"]) for q in d.section["questions"]] == [
        (f"{SID}-q1", [f"{SID}-k1"])
    ]
    assert problems == []  # one idea, one question: a valid section


def test_a_question_aimed_at_a_missing_idea_is_dropped_and_the_next_moves_up() -> None:
    doc = section()
    doc["questions"][0]["targets"] = [f"{SID}-k9"]
    d = draft(doc)
    assert apply_checks(d, CTX) == []
    assert d.dropped[0].item_id == f"{SID}-q1"
    assert [q["id"] for q in d.section["questions"]] == [f"{SID}-q2"]


def test_schema_and_cross_field_violations_are_section_problems() -> None:
    too_long = draft(section(context="x" * 281))
    assert any(p.startswith("schema:") for p in apply_checks(too_long, CTX))
    doc = section()
    doc["questions"][0]["level"] = 1  # levels were removed from the contract
    assert any(p.startswith("schema:") for p in apply_checks(draft(doc), CTX))


def test_the_check_stage_flags_regeneration_then_fails(tmp_path: Path) -> None:
    store = DraftStore("mrk", LocalBlobStore(tmp_path / "drafts"))
    store.write_section_map(
        [SectionMapEntry(id=SID, chapter=7, verse_start=14, verse_end=23, title="T",
                         title_source="bsb-heading")]
    )  # fmt: skip
    doc = section()
    doc["questions"][0]["level"] = 1  # breaks the schema: levels were removed
    d = draft(doc)
    d.stages["generate"] = StageRecord.model_validate(
        {"promptVersion": "v3", "inputHash": "h", "completedAt": "t1", "costUsd": 0.1,
         "status": "done"}
    )  # fmt: skip
    store.write_draft(SID, d)

    class Library:  # just the translations the checks need
        def translation(self, tr: str, book: str) -> Any:
            from thinkbible_pipeline.sources.models import NormalizedTranslationBook

            verses = [{"type": "verse", "number": v, "text": "x"} for v in range(1, 38)
                      if tr == "kjv" or v != 16]  # fmt: skip
            return NormalizedTranslationBook.model_validate(
                {"book": "MRK", "chapters": [{"number": 7, "items": verses}]}
            )

    deps = Deps(store=store, settings=load_settings(), pricing=load_pricing(),
                runner_factory=lambda: FakeRunner(), approve_estimate=lambda _s: True,
                stages=registry(), library=Library())  # type: ignore[arg-type]  # fmt: skip
    result = asyncio.run(run(RunRequest(book="mark", stages=["check"]), deps))
    assert result.exit_code == ExitCode.SECTIONS_FAILED
    first = store.read_draft_or_new(SID)
    assert first.regenerate and first.failed.endswith("(regenerates on the next run)")  # type: ignore[union-attr]
    # After a regeneration (generate records why), a second failure is final.
    first.regenerated_for, first.regenerate = first.regenerate, None
    first.stages["generate"].completed_at = "t2"  # new content: the check runs again
    store.write_draft(SID, first)
    asyncio.run(run(RunRequest(book="mark", stages=["check"]), deps))
    second = store.read_draft_or_new(SID)
    assert second.regenerate is None
    assert second.failed is not None and second.failed.endswith("(after one regeneration)")
