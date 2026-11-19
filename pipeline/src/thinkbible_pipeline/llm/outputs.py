"""What each model call must return (data-model §4): Pydantic models passed to the runner as the
structured ``output_format``.

They're deliberately loose. Lengths, verse ranges and wording rules aren't schema constraints: a
model that broke one would fail validation and burn a retry. The code after each call checks them
instead and drops or repairs the item, recording why (``stages/generate_rules.py``, and the quality
gate in US2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Commentator = Literal["matthew-henry", "jamieson-fausset-brown", "adam-clarke"]
QuestionType = Literal["noticing", "meaning", "application"]


class _Out(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SummaryOut(_Out):
    """``summaries``: one line on what happens in the passage (for the next section's prompt)."""

    summary: str = Field(description="One plain sentence, at most 120 characters.")


class EvidenceOut(_Out):
    commentator: Commentator
    quote: str = Field(
        description="The commentator's own words making this point, 8 to 30 words copied exactly "
        "from their notes: a whole sentence or clause that reads well on its own (readers see it)."
    )


class IdeaOut(_Out):
    kind: Literal["key", "background"] = Field(
        description="key: a deeper meaning the commentators draw from the passage, about God, "
        "Jesus, salvation or following him. background: a fact worth knowing that is not itself "
        "a meaning (another Gospel, the original word, a custom)."
    )
    title: str = Field(description="The point itself, at most 8 words.")
    body: str = Field(description="One or two sentences, at most 30 words.")
    sources: list[Commentator] = Field(description="Every commentator who makes this point.")
    verse_start: int
    verse_end: int
    evidence: list[EvidenceOut] = Field(description="One quote for each commentator in sources.")


class IdeasOut(_Out):
    """``generate`` call 1 (``extract``): the key ideas, context and views-differ notes."""

    key_ideas: list[IdeaOut] = Field(
        description="1 to 5 key ideas and 0 to 2 background ideas: the central meaning first, "
        "then the most important."
    )
    central_idea: int | None = Field(
        default=None,
        description="The number (1 for the first) of the key idea that is the passage's central "
        "meaning: what the passage as a whole is about. Must be a key idea, not background.",
    )
    context: str = Field(
        description="One or two short sentences, at most 35 words: where and when this section "
        "takes place, who is present, and how it follows from the previous section."
    )
    views_differ: str | None = Field(
        default=None,
        description="A neutral note where the commentators or traditions read the passage "
        "differently, at most 55 words; null when they don't.",
    )
    no_prompt: bool = Field(
        description="True only when the commentators give nothing a question could target."
    )
    no_prompt_reason: str | None = None


class AlignVariantOut(_Out):
    """``align``: one question worded for KJV readers (R12)."""

    text: str = Field(
        description="The question with the KJV's words for what it quotes or names; otherwise "
        "unchanged. Return it unchanged if it already reads naturally for a KJV reader."
    )


class IntroOut(_Out):
    """``intro``: the book introduction, from the commentators' prefaces."""

    text: str = Field(
        description="80 to 120 words: who wrote it, to whom, when, why, what to watch for."
    )
    sources: list[Commentator] = Field(description="Every commentator whose preface supports it.")
    evidence: list[EvidenceOut] = Field(description="One quote from each source's preface.")


class QuestionOut(_Out):
    text: str = Field(description="One open question, at most 30 words, ending with '?'.")
    type: QuestionType
    verse_start: int
    verse_end: int
    targets: list[str] = Field(description="IDs of the key ideas this question aims at.")


class QuestionsOut(_Out):
    """``generate`` call 2 (``questions``): candidates in reading order; the grader picks 3."""

    questions: list[QuestionOut] = Field(
        description="Up to 10 candidate questions, in the order a reader should meet them."
    )


class ItemGradeOut(_Out):
    item_id: str
    score: int = Field(description="1 (fails badly) to 5 (excellent), against the rubric.")
    failed_rules: list[str] = Field(
        default_factory=list, description="The rubric lines this item breaks, by their names."
    )
    reason: str = Field(description="One short sentence on the grade, at most 200 characters.")
    focus: Literal["big-picture", "detail"] | None = Field(
        default=None,
        description="Questions only: big-picture or detail (the rubric's `focus`), separate from "
        "the grade.",
    )


class ReviewOut(_Out):
    """``review``: the grader's 1-5 grade for every key idea and question of a section (R16)."""

    items: list[ItemGradeOut]
