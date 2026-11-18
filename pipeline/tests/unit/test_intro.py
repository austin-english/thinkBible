"""The book introduction (2026-11-18): prefaces split from the first note, written once, graded."""

import asyncio
from pathlib import Path
from typing import Any

from thinkbible_pipeline.commentary.gather import book_prefaces, gather
from thinkbible_pipeline.commentary.preface import split_preface
from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.models import SectionMapEntry
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.llm.runner import FakeRunner
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages import registry
from thinkbible_pipeline.stages.base import Deps, run
from thinkbible_pipeline.storage import LocalBlobStore

PREFACE = ("Mark, whose other name was John, was the companion of Peter in his travels and wrote "
           "down what he heard him preach to the believers at Rome. His gospel is short and full "
           "of action, and it moves quickly from one work of Christ to the next, so that the "
           "reader sees the Lord always busy doing good among the people of Galilee and "
           "Judea.")  # fmt: skip
JFB = f"INTRODUCTION\n\n{PREFACE}\n\nCHAPTER 1\n\n1. The beginning--of the good news of the gospel."
CLARKE = (f"Preface to the Gospel According to St. Mark\n\n{PREFACE}\n\n"
          "The preaching of John, Mar 1:1-8. Christ is baptized, Mar 1:9-11.\n\n"
          "Verse 1\n\nThe beginning of the Gospel - the good news itself.")  # fmt: skip
HENRY = (f"Mark\n\n{PREFACE}\n\nIn this chapter we have John's ministry, ver. 1-8.\n\n"
         "The Ministry of John the Baptist.\n\n1 The beginning of the gospel of Jesus Christ.\n\n"
         "Here is the gospel's beginning, the good news of salvation for every "
         "reader.")  # fmt: skip


def test_each_commentators_preface_is_split_from_the_first_note() -> None:
    for name, text, rest_starts in (
        ("jamieson-fausset-brown", JFB, "CHAPTER 1"),
        ("adam-clarke", CLARKE, "The preaching of John"),  # the chapter summary stays
        ("matthew-henry", HENRY, "In this chapter"),
    ):
        preface, rest = split_preface(name, text)
        assert preface is not None and preface.endswith("Galilee and Judea."), name
        assert rest.startswith(rest_starts), (name, rest[:40])
    # No preface: a title only, or text that never reaches the first verse.
    assert (
        split_preface("jamieson-fausset-brown", "THE BOOK OF ESTHER\n\nCHAPTER 1\n\nx")[0] is None
    )
    assert split_preface("matthew-henry", "1 In the beginning God created.") == (
        None, "1 In the beginning God created.")  # fmt: skip


def library(make_library: Any) -> Any:
    verses = [{"type": "verse", "number": v, "text": f"Verse {v}."} for v in range(1, 9)]
    return make_library({
        ("bsb", "MRK"): {"book": "MRK", "chapters": [{"number": 1, "items": verses}]},
        ("kjv", "MRK"): {"book": "MRK", "chapters": [{"number": 1, "items": verses}]},
        ("jamieson-fausset-brown", "MRK"): {"book": "MRK", "chapters": [
            {"number": 1, "items": [{"verse": 1, "verseEnd": 8, "text": JFB}]}]},
        ("adam-clarke", "MRK"): {"book": "MRK", "chapters": [
            {"number": 1, "items": [{"verse": 1, "verseEnd": 8, "text": CLARKE}]}]},
    })  # fmt: skip


ENTRY = SectionMapEntry(id="mrk-1-1", chapter=1, verse_start=1, verse_end=8, title="John",
                        title_source="bsb-heading")  # fmt: skip


def test_sections_no_longer_see_the_preface(make_library: Any) -> None:
    lib = library(make_library)
    excerpt = gather(ENTRY, "MRK", "jamieson-fausset-brown", lib, cap_tokens=8000)
    assert "companion of Peter" not in excerpt.text and "good news of the gospel" in excerpt.text
    prefaces = book_prefaces("MRK", lib, cap_tokens=8000)
    assert set(prefaces) == {"jamieson-fausset-brown", "adam-clarke"}
    assert "companion of Peter" in prefaces["adam-clarke"]


def deps_for(tmp_path: Path, make_library: Any, responses: dict[tuple[str, str], Any]) -> Deps:
    store = DraftStore("mrk", LocalBlobStore(tmp_path / "drafts"))
    store.write_section_map([ENTRY, SectionMapEntry(id="mrk-1-9", chapter=1, verse_start=9,
                                                    verse_end=11, title="Baptism",
                                                    title_source="bsb-heading")])  # fmt: skip
    runner = FakeRunner(responses=responses)
    return Deps(store=store, settings=load_settings(), pricing=load_pricing(),
                runner_factory=lambda: runner, approve_estimate=lambda _s: True,
                stages=registry(), library=library(make_library))  # fmt: skip


INTRO_TEXT = ("Mark, also called John, travelled with Peter and wrote down Peter's preaching for "
              "believers in Rome. His Gospel is the shortest of the four and moves quickly from "
              "one event to the next, so you see Jesus constantly at work, teaching, healing and "
              "calling people. As you read, watch how often Mark says something happened at once, "
              "and how people keep asking who this man really is.")  # fmt: skip


def written(text: str = INTRO_TEXT) -> dict[str, Any]:
    return {"text": text, "sources": ["adam-clarke", "jamieson-fausset-brown"],
            "evidence": [
                {"commentator": "adam-clarke",
                 "quote": "was the companion of Peter in his travels"},
                {"commentator": "jamieson-fausset-brown", "quote": "a quote JFB never wrote here"},
            ]}  # fmt: skip


def graded(score: int) -> dict[str, Any]:
    return {"items": [{"itemId": "intro", "score": score, "reason": f"Reason {score}.",
                       "failedRules": [] if score > 2 else ["faithful"]}]}  # fmt: skip


def test_the_introduction_is_written_once_for_the_book_and_graded(
    tmp_path: Path, make_library: Any
) -> None:
    deps = deps_for(tmp_path, make_library, {("intro.write", "mrk-1-1"): written(),
                                             ("review.intro", "mrk-1-1"): graded(4)})  # fmt: skip
    result = asyncio.run(run(RunRequest(book="mark", stages=["intro"]), deps))
    assert result.exit_code == ExitCode.OK
    runner = deps.runner
    assert isinstance(runner, FakeRunner)
    assert runner.calls == [("intro.write", "mrk-1-1"), ("review.intro", "mrk-1-1")]  # once
    intro = deps.store.read_draft_or_new("mrk-1-1").book_intro
    assert intro is not None and intro.problem is None and intro.grade is not None
    assert intro.introduction is not None
    # JFB's quote isn't in its preface, so JFB is dropped as a source (the evidence check).
    assert intro.introduction["sources"] == ["adam-clarke"]
    assert intro.introduction["quotes"] == [
        {"commentator": "adam-clarke", "text": "…was the companion of Peter in his travels…"}
    ]
    assert deps.store.read_draft_or_new("mrk-1-9").book_intro is None  # other sections: none


def test_a_weak_introduction_is_rewritten_once_then_reported(
    tmp_path: Path, make_library: Any
) -> None:
    responses = {("intro.write", "mrk-1-1"): [written(), written()],
                 ("review.intro", "mrk-1-1"): [graded(2), graded(1)]}  # fmt: skip
    deps = deps_for(tmp_path, make_library, responses)
    asyncio.run(run(RunRequest(book="mark", stages=["intro"]), deps))
    runner = deps.runner
    assert isinstance(runner, FakeRunner)
    assert "A previous attempt was rejected: graded 2: Reason 2." in runner.prompts[2]
    intro = deps.store.read_draft_or_new("mrk-1-1").book_intro
    assert intro is not None and intro.introduction is None
    assert intro.problem == "graded 1: Reason 1."


def test_a_missing_or_failed_introduction_blocks_promotion() -> None:
    from datetime import UTC, datetime

    from thinkbible_pipeline.drafts.models import BookIntro, SectionDraft, StageRecord
    from thinkbible_pipeline.report.scorecard import build_scorecard

    record = {"promptVersion": "v", "inputHash": "h", "completedAt": "t", "costUsd": 0.1,
              "status": "done"}  # fmt: skip
    done = StageRecord.model_validate(record)
    draft = SectionDraft(stages={"generate": done})
    card = build_scorecard("MRK", [ENTRY], {"mrk-1-1": draft}, [], datetime.now(UTC))
    assert "book introduction: not written yet: run the intro stage" in card.blockers
    draft.stages["intro"] = done
    draft.book_intro = BookIntro(problem="graded 2: invents a date")
    card = build_scorecard("MRK", [ENTRY], {"mrk-1-1": draft}, [], datetime.now(UTC))
    assert "book introduction: graded 2: invents a date" in card.blockers
    draft.book_intro = None  # the commentators give no preface: nothing to block
    card = build_scorecard("MRK", [ENTRY], {"mrk-1-1": draft}, [], datetime.now(UTC))
    assert card.introduction_problem is None
