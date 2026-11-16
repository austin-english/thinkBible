"""What code decides after the generate calls (T042): evidence, ranking, levels, pool, IDs."""

from typing import Any

import pytest

from thinkbible_pipeline.drafts.ids import next_id
from thinkbible_pipeline.drafts.models import SectionDraft, SectionMapEntry
from thinkbible_pipeline.llm.outputs import IdeasOut, QuestionOut, QuestionsOut
from thinkbible_pipeline.stages.generate_rules import (
    level_for,
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


def q(text: str, vs: int, ve: int, targets: list[str], qtype: str = "meaning",
      directness: str = "inferred", outside: str = "none") -> dict[str, Any]:  # fmt: skip
    return {"text": text, "type": qtype, "verseStart": vs, "verseEnd": ve, "targets": targets,
            "answerDirectness": directness, "outsideKnowledge": outside}  # fmt: skip


@pytest.mark.parametrize(
    ("fields", "level"),
    [
        ({"vs": 7, "ve": 8, "directness": "stated"}, 1),
        ({"vs": 7, "ve": 7, "directness": "inferred"}, 1),  # a detail to think about: still Level 1
        ({"vs": 6, "ve": 8, "directness": "stated"}, 2),  # three verses
        ({"vs": 1, "ve": 8, "directness": "inferred"}, 2),  # the whole passage
        ({"vs": 7, "ve": 7, "directness": "stated", "outside": "some"}, 2),
        ({"vs": 7, "ve": 7, "directness": "stated", "outside": "required"}, 3),
        ({"vs": 1, "ve": 8, "directness": "beyond"}, 3),
        ({"vs": 7, "ve": 7, "directness": "stated", "qtype": "application"}, 3),
    ],
)
def test_level_rule(fields: dict[str, Any], level: int) -> None:
    raw = q("Why?", fields["vs"], fields["ve"], ["x"], fields.get("qtype", "noticing"),
            fields["directness"], fields.get("outside", "none"))  # fmt: skip
    assert level_for(QuestionOut.model_validate(raw)) == level


def _ideas(n: int) -> list[Any]:
    out = ideas_out(*[
        idea(["matthew-henry", "adam-clarke"],
             {"matthew-henry": "he prepared the way", "adam-clarke": "a baptism of repentance"},
             title=f"idea {i}")
        for i in range(n)
    ])  # fmt: skip
    return process_ideas(out, SECTION, EXCERPTS, SectionDraft())[0]


def test_pool_levels_are_capped_by_the_number_of_ideas() -> None:
    ideas = _ideas(1)
    out = QuestionsOut.model_validate({"questions": [
        q("What does John say?", 7, 7, [ideas[0].id], "noticing", "stated"),
        q("Why does Mark begin here?", 1, 8, [ideas[0].id]),
    ]})  # fmt: skip
    pool = process_questions(out, ideas, SECTION, SectionDraft())
    assert [x.level for x in pool.questions] == [1]
    assert pool.dropped[0].reason == "Level 2 needs at least 2 key ideas (this section has 1)"
    assert pool.problem is None  # one level only: no whole-passage question needed


def test_two_per_level_with_alternates_and_a_cap_of_six() -> None:
    ideas = _ideas(3)
    t = [ideas[0].id]
    out = QuestionsOut.model_validate({"questions": [
        q("Notice one?", 7, 7, t, "noticing", "stated"),
        q("Notice two?", 8, 8, t, "noticing", "stated"),
        q("Notice three?", 6, 6, t, "noticing", "stated"),
        q("Why begin here?", 1, 8, t),
        q("Why the wilderness?", 4, 6, t),
        q("How does it connect?", 1, 8, t, "application"),
        q("What would it mean for you?", 4, 8, t, "application"),
        q("A third connection?", 2, 3, t, "application"),
    ]})  # fmt: skip
    pool = process_questions(out, ideas, SECTION, SectionDraft())
    assert [(x.level, x.is_alternate) for x in pool.questions] == [
        (1, False), (1, True), (2, False), (2, True), (3, False), (3, True)
    ]  # fmt: skip
    assert len(pool.questions) == 6 and pool.problem is None
    assert [d.reason for d in pool.dropped] == [
        "Level 1 already has 2 questions", "Level 3 already has 2 questions"
    ]  # fmt: skip
    assert pool.questions[0].features.verse_span == 1
    assert pool.questions[0].features.agreement == 2


def test_pool_problems_trigger_regeneration() -> None:
    ideas = _ideas(2)
    t = [ideas[0].id]
    no_whole = QuestionsOut.model_validate({"questions": [
        q("What do you notice in this verse?", 7, 7, t, "noticing", "stated"),
        q("Why might John baptize out there?", 4, 6, t),
    ]})  # fmt: skip
    assert process_questions(no_whole, ideas, SECTION, SectionDraft()).problem == (
        "no question on the whole passage"
    )
    no_level_one = QuestionsOut.model_validate(
        {"questions": [q("Why begin the gospel here?", 1, 8, t)]}
    )
    assert process_questions(no_level_one, ideas, SECTION, SectionDraft()).problem == (
        "no Level 1 question"
    )
    untargeted = QuestionsOut.model_validate(
        {"questions": [q("Why begin the gospel here?", 1, 8, ["mrk-1-1-k99"])]}
    )
    pool = process_questions(untargeted, ideas, SECTION, SectionDraft())
    assert pool.problem == "no usable question"
    assert pool.dropped[0].reason == "targets no key idea that was kept"


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


def test_whole_passage_questions_win_a_place_and_alternates_aim_elsewhere() -> None:
    """Regression (Mark 1:12-15, v2): whole-passage questions came after two single-verse Level 2
    questions and were dropped as overflow, so the pool failed for want of one."""
    ideas = _ideas(3)
    a, b = ideas[0].id, ideas[1].id
    out = QuestionsOut.model_validate({"questions": [
        q("What do you make of this detail?", 7, 7, [a], "noticing", "stated"),
        q("Why might this sharper word matter?", 4, 4, [a], "meaning", "inferred", "some"),
        q("How does the wild setting shape the scene?", 5, 5, [a], "meaning", "inferred", "some"),
        q("What holds the whole passage together?", 1, 8, [b]),
        q("How does it connect to your life?", 1, 8, [a], "application"),
    ]})  # fmt: skip
    pool = process_questions(out, ideas, SECTION, SectionDraft())
    level_two = [x for x in pool.questions if x.level == 2]
    assert level_two[0].text == "What holds the whole passage together?"  # primary: whole passage
    assert not level_two[0].is_alternate and level_two[1].is_alternate
    assert level_two[1].targets == [a]  # aimed at another idea than the primary's
    assert pool.problem is None


def test_cut_off_text_is_dropped() -> None:
    """Regression: a double quote in the text ended the JSON string early ("Jesus opens with ")."""
    ideas = _ideas(1)
    out = QuestionsOut.model_validate({"questions": [
        q("Jesus opens with ", 7, 7, [ideas[0].id], "noticing", "stated"),
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
