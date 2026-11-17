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
        description="A short quote, at most 25 words, copied exactly from this commentator's notes."
    )


class IdeaOut(_Out):
    title: str = Field(description="At most 60 characters.")
    body: str = Field(description="One or two sentences, at most 240 characters.")
    sources: list[Commentator] = Field(description="Every commentator who makes this point.")
    verse_start: int
    verse_end: int
    evidence: list[EvidenceOut] = Field(description="One quote for each commentator in sources.")


class IdeasOut(_Out):
    """``generate`` call 1 (``extract``): the key ideas, context and views-differ notes."""

    key_ideas: list[IdeaOut] = Field(description="1 to 5 ideas, the most important first.")
    context: str = Field(description="Two lines: who wrote it, to whom, and why. At most 280.")
    views_differ: str | None = Field(
        default=None,
        description="A neutral note where the commentators or traditions read the passage "
        "differently, at most 400 characters; null when they don't.",
    )
    no_prompt: bool = Field(
        description="True only when the commentators give nothing a question could target."
    )
    no_prompt_reason: str | None = None


class QuestionOut(_Out):
    text: str = Field(description="One open question, at most 200 characters, ending with '?'.")
    type: QuestionType
    verse_start: int
    verse_end: int
    targets: list[str] = Field(description="IDs of the key ideas this question aims at.")


class QuestionsOut(_Out):
    """``generate`` call 2 (``questions``): candidates in reading order; code keeps up to 3."""

    questions: list[QuestionOut] = Field(
        description="Up to 6 candidate questions, in the order a reader should meet them."
    )


class ItemGradeOut(_Out):
    item_id: str
    score: int = Field(description="1 (fails badly) to 5 (excellent), against the rubric.")
    failed_rules: list[str] = Field(
        default_factory=list, description="The rubric lines this item breaks, by their names."
    )
    reason: str = Field(description="One short sentence on the grade, at most 200 characters.")


class ReviewOut(_Out):
    """``review``: the grader's 1-5 grade for every key idea and question of a section (R16)."""

    items: list[ItemGradeOut]
