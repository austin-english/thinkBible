"""Draft and pipeline-state entities (data-model.md §2), stored in ``content/drafts/{book}/``."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from thinkbible_pipeline.jsonio import JsonModel

BookStatus = Literal[
    "sectioned",
    "generating",
    "generated",
    "checked",
    "flagged",
    "ready-for-review",
    "approved",
    "published",
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
    last_published: str | None = None
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


class Flag(JsonModel):
    item_id: str
    source: Literal["check", "review", "levels", "align", "merge", "budget"]
    reason: str
    accepted: bool = False


class Grade(JsonModel):
    score: Annotated[int, Field(ge=1, le=5)]
    notes: str | None = None


class HumanEdit(JsonModel):
    item_id: str
    field: str
    at: str


class StageRecord(JsonModel):
    prompt_version: str
    model: str | None = None  # None for stages without model calls
    input_hash: str
    completed_at: str
    cost_usd: float
    status: Literal["done", "failed"]
    error: str | None = None


class SectionDraft(JsonModel):
    """Working copy (``sections/{id}.json``) and machine copy (``.generated/{id}.json``).

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
    flags: list[Flag] = Field(default_factory=list)
    grades: dict[str, Grade] = Field(default_factory=dict)
    human_edits: list[HumanEdit] = Field(default_factory=list)
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
    stopped_by: Literal["cap", "error"] | None = None


class Approval(JsonModel):
    book: str
    approved_at: str
    drafts_sha256: str
    git_head: str
    accepted_flags: list[str] = Field(default_factory=list)
