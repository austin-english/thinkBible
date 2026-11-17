"""The scorecard: one book's results in numbers (data-model "Scorecard", research R17).

Built from the drafts after a run: how many key ideas and questions were kept or dropped, which
sections failed or have no question, what the run cost. Until the quality gate exists (US2) the
book is "not graded": the pass rates count only what the generate rules kept, and the book can't
be promoted.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from thinkbible_pipeline.drafts.models import RunRecord, SectionDraft, SectionMapEntry
from thinkbible_pipeline.jsonio import JsonModel


class Rate(JsonModel):
    total: int = 0
    passed: int = 0
    dropped: int = 0

    @property
    def pass_rate(self) -> float | None:
        return round(self.passed / self.total, 4) if self.total else None


class SectionIssue(JsonModel):
    section_id: str
    reason: str


class Calibration(JsonModel):
    agreement: float | None = None
    grader_prompt_version: str | None = None
    grader_model: str | None = None
    current: bool = False


class Thresholds(JsonModel):
    min_idea_pass_rate: float | None = None
    min_question_pass_rate: float | None = None


class Scorecard(JsonModel):
    book: str
    run_id: str | None
    generated_at: str
    graded: bool = False  # True once the quality gate (US2) has graded every section
    sections: int = 0
    ideas: Rate = Field(default_factory=Rate)
    questions: Rate = Field(default_factory=Rate)
    idea_pass_rate: float | None = None
    question_pass_rate: float | None = None
    dropped_by_stage: dict[str, int] = Field(default_factory=dict)  # generate, check, review, …
    failed_sections: list[SectionIssue] = Field(default_factory=list)
    not_generated: list[str] = Field(default_factory=list)
    no_prompt: list[SectionIssue] = Field(default_factory=list)
    calibration: Calibration | None = None
    thresholds: Thresholds | None = None
    promotable: bool = False
    promotable_reason: str = ""
    cost_usd: float = 0.0
    models: list[str] = Field(default_factory=list)
    prompt_versions: dict[str, str] = Field(default_factory=dict)


def latest_run(runs: list[RunRecord]) -> tuple[str | None, list[RunRecord]]:
    """The most recent run and its stage records (the run this report belongs to)."""
    if not runs:
        return None, []
    run_id = max(runs, key=lambda r: r.started_at).run_id
    return run_id, [r for r in runs if r.run_id == run_id]


def build_scorecard(
    book: str,
    sections: list[SectionMapEntry],
    drafts: dict[str, SectionDraft],
    runs: list[RunRecord],
    now: datetime,
) -> Scorecard:
    run_id, records = latest_run(runs)
    card = Scorecard(
        book=book,
        run_id=run_id,
        generated_at=now.isoformat(timespec="seconds"),
        sections=len(sections),
        cost_usd=round(sum(r.spent_usd for r in records), 6),
        models=sorted({m for r in records for m in r.models}),
        prompt_versions={k: v for r in records for k, v in r.prompt_versions.items()},
    )
    for entry in sections:
        draft = drafts.get(entry.id)
        if draft is None or "generate" not in draft.stages:
            card.not_generated.append(entry.id)
            continue
        if draft.failed or draft.stages["generate"].status == "failed":
            reason = draft.failed or draft.stages["generate"].error or "failed"
            card.failed_sections.append(SectionIssue(section_id=entry.id, reason=reason))
        section = draft.section
        if section.get("noPrompt"):
            card.no_prompt.append(
                SectionIssue(section_id=entry.id, reason=draft.no_prompt_reason or "")
            )
        card.ideas.passed += len(section.get("keyIdeas", []))
        card.questions.passed += len(section.get("questions", []))
        for d in draft.dropped:
            kind = d.item_id.rsplit("-", 1)[-1][:1]
            (card.ideas if kind == "k" else card.questions).dropped += 1
            card.dropped_by_stage[d.stage] = card.dropped_by_stage.get(d.stage, 0) + 1
    for rate in (card.ideas, card.questions):
        rate.total = rate.passed + rate.dropped
    card.idea_pass_rate = card.ideas.pass_rate
    card.question_pass_rate = card.questions.pass_rate
    card.promotable_reason = (
        "not graded: the quality gate (US2) hasn't run on this book yet" if not card.graded else ""
    )
    return card
