"""The summaries and generate stages (T053, T054) with FakeRunner: no model calls."""

import asyncio
from pathlib import Path
from typing import Any

from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.models import SectionMapEntry
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.llm.runner import FakeRunner
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages import registry
from thinkbible_pipeline.stages.base import Deps, run
from thinkbible_pipeline.storage import LocalBlobStore

S1, S2 = "mrk-1-1", "mrk-1-9"
MAP = [
    SectionMapEntry(id=S1, chapter=1, verse_start=1, verse_end=8, title="John",
                    title_source="bsb-heading"),
    SectionMapEntry(id=S2, chapter=1, verse_start=9, verse_end=13, title="Baptism",
                    title_source="bsb-heading"),
]  # fmt: skip


def translation(code: str, wording: str) -> dict[str, Any]:
    items = [{"type": "verse", "number": v, "text": f"{wording} verse {v}."} for v in range(1, 14)]
    return {"book": code, "chapters": [{"number": 1, "items": items}]}


HENRY = {"book": "MRK", "chapters": [{"number": 1, "items": [
    {"verse": 1, "verseEnd": 8, "text": "John was the morning star to the Sun of righteousness."},
    {"verse": 9, "verseEnd": 13, "text": "Christ was baptized to fulfil all righteousness here."},
]}]}  # fmt: skip
CLARKE = {"book": "MRK", "chapters": [{"number": 1, "items": [
    {"verse": 4, "text": "John's baptism was a baptism of repentance for sinners."},
]}]}  # fmt: skip


def idea(title: str, sources: dict[str, str], vs: int, ve: int) -> dict[str, Any]:
    return {"kind": "key", "title": title, "body": f"{title}.", "sources": list(sources),
            "verseStart": vs,
            "verseEnd": ve,
            "evidence": [{"commentator": c, "quote": q} for c, q in sources.items()]}  # fmt: skip


def q(text: str, vs: int, ve: int, targets: list[str], qtype: str) -> dict[str, Any]:
    return {"text": text, "type": qtype, "verseStart": vs, "verseEnd": ve, "targets": targets}


EXTRACT_S1 = {
    "keyIdeas": [
        idea("John prepares the way", {"matthew-henry": "the morning star to the Sun",
                                       "adam-clarke": "a baptism of repentance for sinners"}, 1, 8),
        idea("Invented", {"jamieson-fausset-brown": "words JFB never wrote here"}, 2, 3),
        idea("Repentance", {"adam-clarke": "a baptism of repentance"}, 4, 5),
    ],
    "context": "Mark wrote for Roman believers.",
    "viewsDiffer": None,
    "noPrompt": False,
}  # fmt: skip
GOOD_POOL = {"questions": [
    q("Why do you think Mark begins with John in the wilderness?", 1, 8, [f"{S1}-k1"], "meaning"),
    q("Why might John call people to be baptized out in the wilderness?", 4, 5, [f"{S1}-k3"],
      "meaning"),
]}  # fmt: skip
UNUSABLE = {"questions": [  # aimed at ideas that weren't kept
    q("What do you make of John's clothes?", 6, 6, [f"{S1}-k2"], "noticing"),
    q("Why does John baptize in the wilderness?", 4, 6, [f"{S1}-k9"], "meaning"),
]}  # fmt: skip
NO_PROMPT = {"keyIdeas": [], "context": "Mark wrote for Roman believers.", "noPrompt": True,
             "noPromptReason": "The commentators only list the names."}  # fmt: skip


def setup(tmp_path: Path, make_library: Any, responses: dict[tuple[str, str], Any]) -> Deps:
    lib = make_library({
        ("bsb", "MRK"): translation("MRK", "BSB"),
        ("kjv", "MRK"): translation("MRK", "KJV"),
        ("matthew-henry", "MRK"): HENRY,
        ("adam-clarke", "MRK"): CLARKE,
    })  # fmt: skip
    store = DraftStore("mrk", LocalBlobStore(tmp_path / "drafts"))
    store.write_section_map(MAP)
    runner = FakeRunner(responses=responses)
    return Deps(
        store=store,
        settings=load_settings(),
        pricing=load_pricing(),
        runner_factory=lambda: runner,
        approve_estimate=lambda _s: True,
        stages=registry(),
        library=lib,
    )


def base_responses() -> dict[tuple[str, str], Any]:
    return {
        ("summaries", S1): {"summary": "John preaches and baptizes in the wilderness."},
        ("summaries", S2): {"summary": "Jesus is baptized and tempted."},
        ("generate.extract", S1): EXTRACT_S1,
        ("generate.questions", S1): GOOD_POOL,
        ("generate.extract", S2): NO_PROMPT,
    }


def test_generate_writes_a_section_with_grounded_ideas_and_a_pool(
    tmp_path: Path, make_library: Any
) -> None:
    deps = setup(tmp_path, make_library, base_responses())
    result = asyncio.run(run(RunRequest(book="mark", stages=["summaries", "generate"]), deps))
    assert result.exit_code == ExitCode.OK
    draft = deps.store.read_draft_or_new(S1)
    section = draft.section
    assert section["ref"] == "Mark 1:1-8" and section["noPrompt"] is False
    ideas = section["keyIdeas"]
    assert [(i["id"], i["agreed"]) for i in ideas] == [(f"{S1}-k1", True), (f"{S1}-k3", False)]
    assert [d.item_id for d in draft.dropped] == [f"{S1}-k2"]  # JFB's invented quote
    assert [(x["id"], x["verseStart"], x["verseEnd"]) for x in section["questions"]] == [
        (f"{S1}-q1", 1, 8), (f"{S1}-q2", 4, 5)
    ]  # fmt: skip
    assert [c["id"] for c in draft.candidates] == [f"{S1}-q1", f"{S1}-q2"]  # for the grader
    assert set(draft.excerpts) == {"matthew-henry", "jamieson-fausset-brown", "adam-clarke"}
    assert draft.excerpts["jamieson-fausset-brown"].tokens == 0  # no JFB notes in this snapshot
    assert draft.stages["generate"].status == "done" and draft.failed is None


def test_prompts_carry_both_translations_the_notes_and_the_previous_summary(
    tmp_path: Path, make_library: Any
) -> None:
    deps = setup(tmp_path, make_library, base_responses())
    asyncio.run(run(RunRequest(book="mark", stages=["summaries", "generate"]), deps))
    runner = deps.runner
    assert isinstance(runner, FakeRunner)
    prompts = dict(zip(runner.calls, runner.prompts, strict=True))
    extract = prompts[("generate.extract", S1)]
    assert '<passage translation="BSB">' in extract and "KJV verse 3." in extract
    assert "the morning star to the Sun" in extract and "(No notes on this section.)" in extract
    assert "(none: this is the start)" in extract
    second = prompts[("generate.extract", S2)]
    assert "John preaches and baptizes in the wilderness." in second  # S1's summary
    questions = prompts[("generate.questions", S1)]
    # No centralIdea given: the first key idea is central, and the writer is told so.
    assert f"{S1}-k1 [CENTRAL MEANING; verses 1-8; agreed: Matthew Henry, Adam Clarke]" in questions
    assert deps.store.read_draft_or_new(S1).central_idea == f"{S1}-k1"
    assert "the morning star to the Sun" in questions  # the writer reads the notes too


def test_no_prompt_sections_skip_the_questions_call(tmp_path: Path, make_library: Any) -> None:
    deps = setup(tmp_path, make_library, base_responses())
    asyncio.run(run(RunRequest(book="mark", stages=["generate"]), deps))
    draft = deps.store.read_draft_or_new(S2)
    assert draft.section["noPrompt"] is True and draft.section["questions"] == []
    assert draft.no_prompt_reason == "The commentators only list the names."
    assert ("generate.questions", S2) not in deps.runner.calls  # type: ignore[attr-defined]


def test_a_broken_pool_is_regenerated_once(tmp_path: Path, make_library: Any) -> None:
    responses = base_responses()
    responses[("generate.questions", S1)] = [UNUSABLE, GOOD_POOL]
    deps = setup(tmp_path, make_library, responses)
    asyncio.run(run(RunRequest(book="mark", stages=["generate"]), deps))
    draft = deps.store.read_draft_or_new(S1)
    assert [x["id"] for x in draft.section["questions"]] == [f"{S1}-q3", f"{S1}-q4"]
    first = [d for d in draft.dropped if d.item_id in (f"{S1}-q1", f"{S1}-q2")]
    assert {d.reason for d in first} == {"targets no key idea that was kept"}
    runner = deps.runner
    assert isinstance(runner, FakeRunner)
    second = [p for c, p in zip(runner.calls, runner.prompts, strict=True)
              if c == ("generate.questions", S1)][1]  # fmt: skip
    assert "A previous attempt broke a rule: no usable question" in second


def test_a_section_that_breaks_the_rules_twice_fails_but_keeps_its_record(
    tmp_path: Path, make_library: Any
) -> None:
    responses = base_responses()
    responses[("generate.questions", S1)] = [UNUSABLE, UNUSABLE]
    deps = setup(tmp_path, make_library, responses)
    result = asyncio.run(run(RunRequest(book="mark", stages=["generate"]), deps))
    assert result.exit_code == ExitCode.SECTIONS_FAILED
    draft = deps.store.read_draft_or_new(S1)
    assert draft.failed == "no usable question"
    assert draft.stages["generate"].status == "failed"
    assert draft.ids.q == 4  # the counter survived the failure: q1-q4 are never given out again


def test_a_note_over_its_limit_asks_once_more(tmp_path: Path, make_library: Any) -> None:
    """Regression (Mark 1:21-28): a 287-character context note failed the check stage and the
    whole section was regenerated. Now generate asks the extract call once more."""
    responses = base_responses()
    responses[("generate.extract", S1)] = [{**EXTRACT_S1, "context": "x" * 281}, EXTRACT_S1]
    # The retry's ideas get new IDs (k4-k6; IDs are never reused), so the questions aim at those.
    responses[("generate.questions", S1)] = {"questions": [
        {**question, "targets": [f"{S1}-k4"]} for question in GOOD_POOL["questions"]
    ]}  # fmt: skip
    deps = setup(tmp_path, make_library, responses)
    result = asyncio.run(run(RunRequest(book="mark", stages=["generate"]), deps))
    assert result.exit_code == ExitCode.OK
    draft = deps.store.read_draft_or_new(S1)
    assert draft.section["context"] == EXTRACT_S1["context"]
    runner = deps.runner
    assert isinstance(runner, FakeRunner)
    extracts = [p for c, p in zip(runner.calls, runner.prompts, strict=True)
                if c == ("generate.extract", S1)]  # fmt: skip
    assert len(extracts) == 2
    assert "the context note was 281 characters (at most 280)" in extracts[1]
    redone = [d for d in draft.dropped if d.reason.startswith("regenerated: the context note")]
    assert [d.item_id for d in redone] == [f"{S1}-k1", f"{S1}-k3"]  # the first attempt's ideas


def test_a_second_run_makes_no_model_calls(tmp_path: Path, make_library: Any) -> None:
    deps = setup(tmp_path, make_library, base_responses())
    request = RunRequest(book="mark", stages=["summaries", "generate"])
    asyncio.run(run(request, deps))
    calls = len(deps.runner.calls)  # type: ignore[attr-defined]
    again = asyncio.run(run(request, deps))
    assert len(deps.runner.calls) == calls  # type: ignore[attr-defined]
    assert all(s.skipped == 2 and s.done == 0 for s in again.stages)
