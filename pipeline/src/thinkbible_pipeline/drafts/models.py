"""Draft and pipeline-state entities (data-model.md §2), stored in ``content/drafts/{book}/``."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from thinkbible_pipeline.jsonio import JsonModel

# data-model §2 state machine (revised 2026-11-10: automatic gate; 2026-11-13: draft → live).
BookStatus = Literal[
    "sectioned",
    "generating",
    "generated",
    "gated",
    "failed",
    "published-draft",
    "promoted",
]


class BookRef(JsonModel):
    id: str  # USFM code
    name: str


class IdCounter(JsonModel):
    """The last key idea (``k``) and question (``q``) number given out in a section (R13)."""

    k: Annotated[int, Field(ge=0)] = 0
    q: Annotated[int, Field(ge=0)] = 0


class BookState(JsonModel):
    book: BookRef
    status: BookStatus
    draft_version: str | None = None  # the version currently on the draft channel
    last_promoted: str | None = None  # the last version promoted to the live channel


class SectionMapEntry(JsonModel):
    id: str
    chapter: int
    verse_start: int
    verse_end: int
    title: str
    title_source: Literal["bsb-heading", "split", "human"]
    henry_divisions: list[int] = Field(default_factory=list)


class SectionMap(JsonModel):
    sections: list[SectionMapEntry]


class Evidence(JsonModel):
    commentator: str
    quote: str


class ExcerptRecord(JsonModel):
    """A record of what a model was given, never the text itself."""

    sha256: str
    tokens: int
    items: list[str] = Field(default_factory=list)  # parts included: "MRK 1:1-8", "MAT 12:9-21"
    cross_refs: list[str] = Field(default_factory=list)
    trimmed: bool = False


class CheckResult(JsonModel):
    item_id: str
    check: str
    ok: bool
    detail: str | None = None


class DroppedItem(JsonModel):
    """An item the quality gate removed, with why and the item as it was generated (R16)."""

    item_id: str
    # "levels": the level check, removed 2026-11-17; kept so older drafts still load.
    stage: Literal["generate", "check", "review", "levels", "align"]
    reason: str
    item: dict[str, Any] = Field(default_factory=dict)


class Grade(JsonModel):
    score: Annotated[int, Field(ge=1, le=5)]
    notes: str | None = None
    focus: str | None = None  # questions: "big-picture" or "detail" (review/v14, 2026-11-19)


class StageRecord(JsonModel):
    prompt_version: str
    model: str | None = None  # None for stages without model calls
    input_hash: str
    completed_at: str
    cost_usd: float
    status: Literal["done", "failed"]
    error: str | None = None


class BookIntro(JsonModel):
    """The book introduction, kept on the draft of the book's first section (``stages/intro.py``).

    ``introduction`` is the publishable BookIntroduction (text, sources, quotes), or None when the
    commentators give no preface or the introduction failed (``problem`` says why).
    """

    introduction: dict[str, Any] | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    grade: Grade | None = None
    problem: str | None = None


class SectionDraft(JsonModel):
    """One section's pipeline state (``sections/{id}.json``). Nobody edits it by hand.

    ``section`` holds the publishable Section fields as they're built up stage by stage, so it's a
    plain JSON object here. ``publish`` validates it against the Section contract.
    """

    @model_validator(mode="before")
    @classmethod
    def _forget_levels(cls, data: Any) -> Any:
        """Drafts written before levels were removed (2026-11-17) still load; the next
        ``generate`` replaces their content. The old ``levels`` stage record is forgotten too."""
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in ("features", "levelChanges")}
            stages = data.get("stages")
            if isinstance(stages, dict) and "levels" in stages:
                data["stages"] = {k: v for k, v in stages.items() if k != "levels"}
        return data

    section: dict[str, Any] = Field(default_factory=dict)
    # Only ever increases, so IDs are never reused, even for items dropped before publishing
    # (R13). Kept per section, not in book.json: sections run in parallel in the cloud.
    ids: IdCounter = Field(default_factory=IdCounter)
    evidence: dict[str, list[Evidence]] = Field(default_factory=dict)
    excerpts: dict[str, ExcerptRecord] = Field(default_factory=dict)
    summary: str | None = None
    no_prompt_reason: str | None = None
    checks: list[CheckResult] = Field(default_factory=list)
    grades: dict[str, Grade] = Field(default_factory=dict)
    dropped: list[DroppedItem] = Field(default_factory=list)
    # Only on the book's first section: the book introduction (the first post of the book).
    book_intro: BookIntro | None = None
    # Every question that passed generate's checks, in the writer's order (not published). The
    # grader scores them all and ``review`` keeps the best (R11, 2026-11-17).
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    # What ``align`` added, for the report (R12, R3): each KJV variant with the words that called
    # for it, each variant the model wrote that the checks refused, and each manuscript note.
    alignment: list[dict[str, Any]] = Field(default_factory=list)
    # The key idea that is the passage's central meaning: ``review`` gives its best question the
    # first place, if one grades 4 or more (2026-11-18).
    central_idea: str | None = None
    failed: str | None = None  # why the section failed after one regeneration (FR-018)
    # Set by a gate stage when the section broke a rule after generate ran: the next run's
    # generate regenerates it once (its inputs include this), then clears it (FR-018).
    regenerate: str | None = None
    # Why the current content was regenerated, if it was: a second failure is then final.
    regenerated_for: str | None = None
    stages: dict[str, StageRecord] = Field(default_factory=dict)


class SectionCounts(JsonModel):
    done: int = 0
    skipped: int = 0
    failed: int = 0


class TokenCounts(JsonModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


class RunRecord(JsonModel):
    run_id: str
    book: str
    stage: str
    started_at: str
    ended_at: str
    sections: SectionCounts
    estimate_usd: float
    cap_usd: float | None = None
    spent_usd: float
    tokens: TokenCounts
    models: list[str]
    prompt_versions: dict[str, str]
    code_version: str | None = None  # git HEAD of the bundle (or working tree for --local)
    stopped_by: Literal["cap", "error"] | None = None
