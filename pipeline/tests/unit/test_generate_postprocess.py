"""What code decides after the generate calls (T042): evidence, ranking, questions, IDs."""

from typing import Any

from thinkbible_pipeline.drafts.ids import next_id
from thinkbible_pipeline.drafts.models import SectionDraft, SectionMapEntry
from thinkbible_pipeline.llm.outputs import IdeasOut, QuestionsOut
from thinkbible_pipeline.stages.generate_rules import (
    normalize,
    process_ideas,
    process_questions,
    quote_found,
)

SECTION = SectionMapEntry(
    id="mrk-1-1", chapter=1, verse_start=1, verse_end=8, title="T", title_source="bsb-heading"
)
EXCERPTS = {
    "matthew-henry": "John was the morning star to the Sun of righteousness; he prepared the way.",
    "jamieson-fausset-brown": "The beginning of the gospel--that is, the good news of salvation.",
    "adam-clarke": "John's baptism was a baptism of repentance, preparing men for the Messiah.",
}


def idea(sources: list[str], quotes: dict[str, str], vs: int = 1, ve: int = 8, title: str = "I"
         ) -> dict[str, Any]:  # fmt: skip
    return {
        "title": title,
        "body": "Body.",
        "sources": sources,
        "verseStart": vs,
        "verseEnd": ve,
        "evidence": [{"commentator": c, "quote": q} for c, q in quotes.items()],
    }


def ideas_out(*ideas: dict[str, Any]) -> IdeasOut:
    return IdeasOut.model_validate(
        {"keyIdeas": list(ideas), "context": "Mark wrote for Romans.", "noPrompt": False}
    )


def test_normalized_quotes_match_despite_punctuation_and_case() -> None:
    assert (
        normalize("“The beginning of the Gospel”—that is,") == "the beginning of the gospel that is"
    )
    assert quote_found("the BEGINNING of the gospel, that is", EXCERPTS["jamieson-fausset-brown"])
    assert not quote_found(
        "the beginning of the gospel of Jesus", EXCERPTS["jamieson-fausset-brown"]
    )
    assert not quote_found("he prepared", EXCERPTS["matthew-henry"])  # too short to prove anything


def test_evidence_check_removes_unbacked_sources_and_rejects_empty_ideas() -> None:
    draft = SectionDraft()
    out = ideas_out(
        idea(["matthew-henry", "adam-clarke"],
             {"matthew-henry": "the morning star to the Sun",
              "adam-clarke": "a quote Clarke never wrote"}),
        idea(["jamieson-fausset-brown"], {"jamieson-fausset-brown": "not in the notes at all"}),
    )  # fmt: skip
    kept, dropped = process_ideas(out, SECTION, EXCERPTS, draft)
    assert [(i.id, i.sources, i.agreed) for i in kept] == [("mrk-1-1-k1", ["matthew-henry"], False)]
    assert kept[0].evidence[0].quote == "the morning star to the Sun"
    assert [(d.item_id, d.stage) for d in dropped] == [("mrk-1-1-k2", "generate")]
    assert dropped[0].reason.startswith("evidence:")


def test_agreed_ideas_rank_first_and_at_most_five_are_kept() -> None:
    single = {"matthew-henry": "he prepared the way"}
    both = {"matthew-henry": "he prepared the way", "adam-clarke": "a baptism of repentance"}
    out = ideas_out(
        idea(["matthew-henry"], single, title="one"),
        idea(["matthew-henry", "adam-clarke"], both, title="two"),
        *[idea(["matthew-henry"], single, title=f"extra {n}") for n in range(4)],
    )
    kept, dropped = process_ideas(out, SECTION, EXCERPTS, SectionDraft())
    assert [i.title for i in kept][:2] == ["two", "one"] and kept[0].agreed
    assert len(kept) == 5 and [d.reason for d in dropped] == ["more than 5 key ideas"]


def test_ideas_outside_the_section_are_dropped() -> None:
    out = ideas_out(idea(["matthew-henry"], {"matthew-henry": "he prepared the way"}, vs=7, ve=12))
    kept, dropped = process_ideas(out, SECTION, EXCERPTS, SectionDraft())
    assert kept == [] and "outside the section" in dropped[0].reason


def q(text: str, vs: int, ve: int, targets: list[str], qtype: str = "meaning") -> dict[str, Any]:
    return {"text": text, "type": qtype, "verseStart": vs, "verseEnd": ve, "targets": targets}


def _ideas(n: int) -> list[Any]:
    out = ideas_out(*[
        idea(["matthew-henry", "adam-clarke"],
             {"matthew-henry": "he prepared the way", "adam-clarke": "a baptism of repentance"},
             title=f"idea {i}")
        for i in range(n)
    ])  # fmt: skip
    return process_ideas(out, SECTION, EXCERPTS, SectionDraft())[0]


def texts(pool: Any) -> list[str]:
    return [x.text for x in pool.questions]


def test_one_question_per_idea_at_most_three_in_the_models_order() -> None:
    one = _ideas(1)
    out = QuestionsOut.model_validate({"questions": [
        q("Why does Mark begin here?", 1, 8, [one[0].id]),
        q("What do you make of John's words?", 7, 7, [one[0].id]),
    ]})  # fmt: skip
    pool = process_questions(out, one, SECTION, SectionDraft())
    assert texts(pool) == ["Why does Mark begin here?"] and pool.problem is None
    assert pool.dropped[0].reason == "more than 1 questions passed; the earlier ones were kept"

    ideas = _ideas(4)
    a, b, c, d = (i.id for i in ideas)
    out = QuestionsOut.model_validate({"questions": [
        q("Why does Mark begin here?", 1, 8, [a]),
        q("What is John pointing to?", 7, 8, [b]),
        q("How does this reach your own life?", 4, 8, [c], "application"),
        q("A fourth question?", 2, 3, [d]),
    ]})  # fmt: skip
    pool = process_questions(out, ideas, SECTION, SectionDraft())
    assert texts(pool) == [
        "Why does Mark begin here?",
        "What is John pointing to?",
        "How does this reach your own life?",
    ]
    assert [x.id for x in pool.questions] == ["mrk-1-1-q1", "mrk-1-1-q2", "mrk-1-1-q3"]
    assert pool.questions[0].publishable() == {
        "id": "mrk-1-1-q1", "type": "meaning", "verseStart": 1, "verseEnd": 8,
        "text": "Why does Mark begin here?", "targets": [a], "status": "active",
    }  # fmt: skip


def test_questions_on_a_new_idea_come_before_repeats() -> None:
    ideas = _ideas(3)
    a, b = ideas[0].id, ideas[1].id
    out = QuestionsOut.model_validate({"questions": [
        q("Why does Mark begin here?", 1, 8, [a]),
        q("What else about that idea?", 2, 3, [a]),
        q("What is John pointing to?", 7, 8, [b]),
        q("And one more on the first idea?", 4, 4, [a]),
    ]})  # fmt: skip
    pool = process_questions(out, ideas, SECTION, SectionDraft())
    # The repeat waits for a place the new ideas don't fill; the order stays the model's.
    assert texts(pool) == [
        "Why does Mark begin here?", "What else about that idea?", "What is John pointing to?"
    ]  # fmt: skip


def test_a_whole_passage_question_is_kept_when_one_passed() -> None:
    ideas = _ideas(3)
    a, b, c = (i.id for i in ideas)
    out = QuestionsOut.model_validate({"questions": [
        q("What do you make of this detail?", 7, 7, [a]),
        q("Why might this word matter?", 4, 4, [b]),
        q("How does the wild setting shape it?", 5, 5, [c]),
        q("What holds the whole passage together?", 1, 8, [a, b]),
    ]})  # fmt: skip
    pool = process_questions(out, ideas, SECTION, SectionDraft())
    assert texts(pool) == [
        "What do you make of this detail?", "Why might this word matter?",
        "What holds the whole passage together?",
    ]  # fmt: skip


def test_no_usable_question_triggers_regeneration() -> None:
    ideas = _ideas(2)
    untargeted = QuestionsOut.model_validate(
        {"questions": [q("Why begin the gospel here?", 1, 8, ["mrk-1-1-k99"])]}
    )
    pool = process_questions(untargeted, ideas, SECTION, SectionDraft())
    assert pool.problem == "no usable question"
    assert pool.dropped[0].reason == "targets no key idea that was kept"
    # Single-verse questions are fine on their own: there is no whole-passage rule.
    detail = QuestionsOut.model_validate(
        {"questions": [q("What do you make of this?", 7, 7, [ideas[0].id])]}
    )
    assert process_questions(detail, ideas, SECTION, SectionDraft()).problem is None


def test_ids_are_never_reused_even_for_dropped_items() -> None:
    draft = SectionDraft()
    out = ideas_out(
        idea(["matthew-henry"], {"matthew-henry": "not in the notes"}),
        idea(["matthew-henry"], {"matthew-henry": "he prepared the way"}),
    )
    kept, dropped = process_ideas(out, SECTION, EXCERPTS, draft)
    assert dropped[0].item_id == "mrk-1-1-k1" and kept[0].id == "mrk-1-1-k2"
    # A later run of the same section continues from the stored counter.
    again, _ = process_ideas(out, SECTION, EXCERPTS, draft)
    assert again[0].id == "mrk-1-1-k4"
    assert next_id(draft, "mrk-1-1", "q") == "mrk-1-1-q1" and draft.ids.k == 4


def test_cut_off_text_is_dropped() -> None:
    """Regression: a double quote in the text ended the JSON string early ("Jesus opens with ")."""
    ideas = _ideas(1)
    out = QuestionsOut.model_validate({"questions": [
        q("Jesus opens with ", 7, 7, [ideas[0].id], "noticing"),
    ]})  # fmt: skip
    pool = process_questions(out, ideas, SECTION, SectionDraft())
    assert pool.questions == [] and pool.dropped[0].reason.startswith("incomplete question")
    cut = ideas_out(
        {**idea(["matthew-henry"], {"matthew-henry": "he prepared the way"}), "body": "Jesus says "}
    )
    kept, dropped = process_ideas(cut, SECTION, EXCERPTS, SectionDraft())
    assert kept == [] and dropped[0].reason.startswith("incomplete text")


def test_quotes_may_skip_citations_and_run_long() -> None:
    """Regression (Mark 1:12-15, v3): verbatim quotes of 32-37 words, and one that left out
    JFB's "(Mr 1:12)", failed the check and took three of four ideas with them."""
    jfb = 'that "He was with the wild beasts" (Mr 1:12), no doubt to add terror to solitude.'
    assert quote_found('"He was with the wild beasts," no doubt to add terror to solitude', jfb)
    long_note = " ".join(f"word{n}" for n in range(60))
    assert quote_found(" ".join(f"word{n}" for n in range(5, 45)), long_note)
    excerpts = {**EXCERPTS, "matthew-henry": long_note}
    out = ideas_out(
        idea(["matthew-henry"], {"matthew-henry": " ".join(f"word{n}" for n in range(40))})
    )
    kept, _ = process_ideas(out, SECTION, excerpts, SectionDraft())
    assert len(kept[0].evidence[0].quote.split()) == 30  # stored short, still verbatim
