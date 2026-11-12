"""Draft and pipeline-state entities (data-model.md §2), stored in ``content/drafts/{book}/``."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from thinkbible_pipeline.jsonio import JsonModel

# data-model §2 state machine (revised 2026-11-10: automatic gate, dev → production).
BookStatus = Literal[
    "sectioned",
    "generating",
    "generated",
    "gated",
    "failed",
    "published-dev",
    "promoted",
]


class BookRef(JsonModel):
    id: str  # USFM code
    name: str


class IdCounter(JsonModel):
    k: Annotated[int, Field(ge=0)] = 0
    q: Annotated[int, Field(ge=0)] = 0


class BookState(JsonModel):
    book: BookRef
    status: BookStatus
    dev_version: str | None = None  # the version currently on dev
    last_promoted: str | None = None  # the last version promoted to production
    # Only ever increases (R13): IDs are never reused.
    id_counters: dict[str, IdCounter] = Field(default_factory=dict)


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
    items: list[int] = Field(default_factory=list)  # commentary verse keys included
    cross_refs: list[str] = Field(default_factory=list)
    trimmed: bool = False


class QuestionFeatures(JsonModel):
    answer_directness: Literal["stated", "inferred", "beyond"]
    outside_knowledge: Literal["none", "some", "required"]
    verse_span: int
    agreement: int


class CheckResult(JsonModel):
    item_id: str
    check: str
    ok: bool
    detail: str | None = None


class DroppedItem(JsonModel):
    """An item the quality gate removed, with why and the item as it was generated (R16)."""

    item_id: str
    stage: Literal["check", "review", "levels", "align"]
    reason: str
    item: dict[str, Any] = Field(default_factory=dict)


class LevelChange(JsonModel):
    question_id: str
    from_level: int = Field(alias="from")
    to_level: int = Field(alias="to")
    reason: str


class Grade(JsonModel):
    score: Annotated[int, Field(ge=1, le=5)]
    notes: str | None = None


class StageRecord(JsonModel):
    prompt_version: str
    model: str | None = None  # None for stages without model calls
    input_hash: str
    completed_at: str
    cost_usd: float
    status: Literal["done", "failed"]
    error: str | None = None


class SectionDraft(JsonModel):
    """One section's pipeline state (``sections/{id}.json``). Nobody edits it by hand.

    ``section`` holds the publishable Section fields as they're built up stage by stage, so it's a
    plain JSON object here. ``publish`` validates it against the Section contract.
    """

    section: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, list[Evidence]] = Field(default_factory=dict)
    excerpts: dict[str, ExcerptRecord] = Field(default_factory=dict)
    summary: str | None = None
    no_prompt_reason: str | None = None
    features: dict[str, QuestionFeatures] = Field(default_factory=dict)
    checks: list[CheckResult] = Field(default_factory=list)
    grades: dict[str, Grade] = Field(default_factory=dict)
    dropped: list[DroppedItem] = Field(default_factory=list)
    level_changes: list[LevelChange] = Field(default_factory=list)
    failed: str | None = None  # why the section failed after one regeneration (FR-018)
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
