"""The scorecard: one book's results in numbers (data-model "Scorecard", R16, R17, T097).

Built from the drafts after a run. Pass rates are the grader's: of the items it graded, the share
graded above ``review_flag_threshold``, counted before its drops (R16). The book is promotable only
when every section is generated and graded, none failed, both pass rates reach the gate's
thresholds, and the grader's calibration for its current prompt and model is good enough.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from thinkbible_pipeline.config import Settings, load_settings
from thinkbible_pipeline.drafts.models import RunRecord, SectionDraft, SectionMapEntry
from thinkbible_pipeline.gate.calibration import CalibrationSet
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
    items: int = 0
    grader_prompt_version: str | None = None
    grader_model: str | None = None
    current: bool = False  # a result exists for the grader prompt and model in use


class Thresholds(JsonModel):
    min_idea_pass_rate: float | None = None
    min_question_pass_rate: float | None = None


class Scorecard(JsonModel):
    book: str
    run_id: str | None
    generated_at: str
    graded: bool = False  # every generated section has been through the grader
    sections: int = 0
    ideas: Rate = Field(default_factory=Rate)  # graded key ideas: passed = above the threshold
    questions: Rate = Field(default_factory=Rate)
    kept_ideas: int = 0  # in the sections now, after every drop
    kept_questions: int = 0
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
    blockers: list[str] = Field(default_factory=list)  # every unmet condition for promotion
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
    *,
    settings: Settings | None = None,
    calibration: CalibrationSet | None = None,
    grader: tuple[str, str] | None = None,  # (prompt version tag, model) of the grader in use
) -> Scorecard:
    settings = settings or load_settings()
    threshold = settings.review_flag_threshold
    run_id, records = latest_run(runs)
    card = Scorecard(
        book=book,
        run_id=run_id,
        generated_at=now.isoformat(timespec="seconds"),
        sections=len(sections),
        cost_usd=round(sum(r.spent_usd for r in records), 6),
        models=sorted({m for r in records for m in r.models}),
        prompt_versions={k: v for r in records for k, v in r.prompt_versions.items()},
        thresholds=Thresholds(
            min_idea_pass_rate=settings.gate.min_idea_pass_rate,
            min_question_pass_rate=settings.gate.min_question_pass_rate,
        ),
    )
    ungraded = 0
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
        card.kept_ideas += len(section.get("keyIdeas", []))
        card.kept_questions += len(section.get("questions", []))
        has_items = bool(section.get("keyIdeas") or section.get("questions"))
        review = draft.stages.get("review")
        if has_items and (review is None or review.status != "done"):
            ungraded += 1
        for item_id, grade in draft.grades.items():
            kind = item_id.rsplit("-", 1)[-1][:1]
            if kind not in ("k", "q"):
                continue  # the context and views-differ notes: graded, but not in the pass rates
            rate = card.ideas if kind == "k" else card.questions
            rate.total += 1
            if grade.score > threshold:
                rate.passed += 1
            else:
                rate.dropped += 1
        for d in draft.dropped:
            card.dropped_by_stage[d.stage] = card.dropped_by_stage.get(d.stage, 0) + 1
    card.graded = bool(sections) and not card.not_generated and ungraded == 0
    card.idea_pass_rate = card.ideas.pass_rate
    card.question_pass_rate = card.questions.pass_rate

    if grader is not None:
        version, model = grader
        result = (calibration or CalibrationSet()).result_for(version, model)
        card.calibration = Calibration(
            agreement=result.agreement if result else None,
            items=result.items if result else 0,
            grader_prompt_version=version,
            grader_model=model,
            current=result is not None,
        )
    card.blockers = _blockers(card, settings, ungraded)
    card.promotable = not card.blockers
    card.promotable_reason = "; ".join(card.blockers)
    return card


def _blockers(card: Scorecard, settings: Settings, ungraded: int) -> list[str]:
    gate = settings.gate
    out = []
    if card.not_generated:
        out.append(f"{len(card.not_generated)} sections not generated")
    if ungraded:
        out.append(f"{ungraded} sections not graded")
    if card.failed_sections:
        out.append(f"{len(card.failed_sections)} sections failed")
    if card.idea_pass_rate is not None and card.idea_pass_rate < gate.min_idea_pass_rate:
        out.append(f"idea pass rate {card.idea_pass_rate:.2f} < {gate.min_idea_pass_rate:.2f}")
    if (
        card.question_pass_rate is not None
        and card.question_pass_rate < gate.min_question_pass_rate
    ):
        out.append(
            f"question pass rate {card.question_pass_rate:.2f} < {gate.min_question_pass_rate:.2f}"
        )
    cal = card.calibration
    if cal is None or not cal.current:
        out.append("no grader calibration for the current grader prompt and model; run `calibrate`")
    elif cal.items < gate.min_calibration_items:
        out.append(f"calibration has {cal.items} items (needs {gate.min_calibration_items})")
    elif (cal.agreement or 0) < gate.min_agreement:
        out.append(
            f"grader calibration: agreement {cal.agreement:.2f} < {gate.min_agreement:.2f}; "
            "adjust prompts/review and run `calibrate`"
        )
    return out
