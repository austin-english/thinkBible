"""Translation alignment (T076, R3, R12): what code flags, and what the align stage does with it."""

import asyncio
import copy
from pathlib import Path
from typing import Any

from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.models import SectionDraft, SectionMapEntry, StageRecord
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.llm.runner import FakeRunner
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sources.models import NormalizedTranslationBook
from thinkbible_pipeline.stages import registry
from thinkbible_pipeline.stages.align import variant_problem
from thinkbible_pipeline.stages.align_rules import bsb_only_words, manuscript_candidates
from thinkbible_pipeline.stages.base import Deps, run
from thinkbible_pipeline.storage import LocalBlobStore

BSB_7 = "I am not worthy to stoop down and untie the straps of His sandals."
KJV_7 = "The latchet of whose shoes I am not worthy to stoop down and unloose."


def test_a_quoted_phrase_the_kjv_words_differently_is_flagged() -> None:
    quoted = "John calls himself unfit to untie the 'sandals' of the one coming. Why say so?"
    assert bsb_only_words(quoted, BSB_7, KJV_7) == ["sandal"]
    # The same words unquoted are plain modern English for either reader ("crowd", "boat"...).
    plain = "John says he is not worthy to untie the sandals of the one coming. Why say so?"
    assert bsb_only_words(plain, BSB_7, KJV_7) == []
    # A quoted word both translations use needs nothing.
    assert bsb_only_words("He says he is not 'worthy.' Why?", BSB_7, KJV_7) == []


def test_a_name_the_kjv_spells_differently_is_flagged() -> None:
    bsb_book = "Moses and Elijah appeared. Bartimaeus sat by the road."
    kjv_book = "There appeared unto them Elias with Moses. Blind Bartimæus sat by the highway side."
    question = "Moses and Elijah talk with Jesus. Why these two?"
    assert bsb_only_words(question, "", "", bsb_book, kjv_book) == ["elijah"]
    # The KJV's joined letters are the same name: Bartimæus is Bartimaeus.
    assert bsb_only_words("Why does Bartimaeus shout?", "", "", bsb_book, kjv_book) == []


def _book(verses: dict[int, int], omit: set[tuple[int, int]], notes: list[dict[str, Any]]) -> Any:
    return NormalizedTranslationBook.model_validate({"book": "MRK", "chapters": [
        {"number": c, "items": [{"type": "verse", "number": v, "text": f"Verse {v}."}
                                for v in range(1, n + 1) if (c, v) not in omit],
         "footnotes": [f for f in notes if f["chapter"] == c]}
        for c, n in verses.items()]})  # fmt: skip


def test_manuscript_notes_for_missing_verses_and_an_early_ending() -> None:
    footnotes = [
        {"noteId": 1, "chapter": 7, "verse": 15,
         "text": "BYZ and TR include 16 If anyone has ears to hear, let him hear."},
        {"noteId": 2, "chapter": 16, "verse": 8,
         "text": "Some early manuscripts end the Gospel of Mark after verse 8."},
        {"noteId": 3, "chapter": 1, "verse": 2, "text": "BYZ and TR in the prophets:"},
    ]  # fmt: skip
    bsb = _book({1: 8, 7: 23, 16: 20}, {(7, 16)}, footnotes)
    kjv = _book({1: 8, 7: 23, 16: 20}, set(), [])
    [verse] = manuscript_candidates(bsb, kjv, "Mark", 7, 14, 23)
    assert (verse.verse_start, verse.verse_end) == (16, 16)
    assert verse.text.startswith("Verse 16 is in the KJV but not in the BSB")
    [ending] = manuscript_candidates(bsb, kjv, "Mark", 16, 9, 13)
    assert (ending.verse_start, ending.verse_end) == (9, 20)
    assert ending.text.startswith("Some early manuscripts end Mark after verse 8.")
    assert manuscript_candidates(bsb, kjv, "Mark", 16, 1, 8) == []  # the ending's own section
    assert manuscript_candidates(bsb, kjv, "Mark", 1, 1, 8) == []  # a wording-level footnote
    assert all(len(c.text) <= 280 for c in (verse, ending))


def test_a_variant_must_differ_and_read_as_a_question() -> None:
    original = "Why might he say 'I am willing'?"
    assert variant_problem(original, original) == "unchanged"
    assert variant_problem("Why might he say 'I will'.", original) == "doesn't end with '?'"
    assert variant_problem('Why might he say "I will"?', original) == "uses double quotation marks"
    assert variant_problem("Why might he say 'I will'?", original) is None


SID = "mrk-1-1"


def _deps(tmp_path: Path, make_library: Any, answers: list[dict[str, str]]) -> Deps:
    def book(tr: str) -> dict[str, Any]:
        text = {7: BSB_7 if tr == "bsb" else KJV_7}
        return {"book": "MRK", "chapters": [{"number": 1, "items": [
            {"type": "verse", "number": v, "text": text.get(v, f"Verse {v}.")}
            for v in range(1, 9)]}]}  # fmt: skip

    lib = make_library({("bsb", "MRK"): book("bsb"), ("kjv", "MRK"): book("kjv")})
    store = DraftStore("mrk", LocalBlobStore(tmp_path / "drafts"))
    entry = SectionMapEntry(id=SID, chapter=1, verse_start=1, verse_end=8, title="John",
                            title_source="bsb-heading")  # fmt: skip
    store.write_section_map([entry])
    quoted = {"id": f"{SID}-q1", "type": "meaning", "verseStart": 7, "verseEnd": 7,
              "text": "John will not untie the 'sandals' of the one coming. What is he saying?",
              "targets": [f"{SID}-k1"], "status": "active"}  # fmt: skip
    plain = {**quoted, "id": f"{SID}-q2", "text": "Why might John feel unworthy of the one coming?"}
    draft = SectionDraft(candidates=[quoted, plain], section={
        "id": SID, "chapter": 1, "verseStart": 1, "verseEnd": 8,
        "questions": [copy.deepcopy(quoted)], "manuscriptNotes": []})  # fmt: skip
    draft.stages["generate"] = StageRecord(prompt_version="v", input_hash="h", completed_at="t",
                                           cost_usd=0.1, status="done")  # fmt: skip
    store.write_draft(SID, draft)
    runner = FakeRunner(responses={(f"align.{SID}-q1", SID): answers})  # one call per question
    return Deps(store=store, settings=load_settings(), pricing=load_pricing(),
                runner_factory=lambda: runner, approve_estimate=lambda _s: True,
                stages=registry(), library=lib)  # fmt: skip


def test_the_stage_writes_a_kjv_variant_only_where_needed(
    tmp_path: Path, make_library: Any
) -> None:
    kjv = "John will not unloose the 'shoes' of the one coming. What is he saying?"
    deps = _deps(tmp_path, make_library, [{"text": kjv}])
    result = asyncio.run(run(RunRequest(book="mark", stages=["align"]), deps))
    assert result.exit_code == 0, result.stages
    draft = deps.store.read_draft_or_new(SID)
    assert draft.candidates[0]["textByTranslation"] == {"kjv": kjv}
    assert "textByTranslation" not in draft.candidates[1]  # nothing to change: no model call
    assert draft.section["questions"][0]["textByTranslation"] == {"kjv": kjv}
    assert deps.runner.calls == [(f"align.{SID}-q1", SID)]  # type: ignore[attr-defined]
    assert [a["kind"] for a in draft.alignment] == ["variant"]


def test_a_variant_that_fails_the_checks_is_logged_not_kept(
    tmp_path: Path, make_library: Any
) -> None:
    deps = _deps(tmp_path, make_library, [{"text": "John will not unloose the 'shoes'."}])
    asyncio.run(run(RunRequest(book="mark", stages=["align"]), deps))
    draft = deps.store.read_draft_or_new(SID)
    assert "textByTranslation" not in draft.candidates[0]
    assert draft.alignment[0]["kind"] == "refused"
    assert draft.alignment[0]["reason"] == "doesn't end with '?'"
