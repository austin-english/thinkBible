"""The scorecard: one book's results in numbers (data-model "Scorecard", R16, R17, T097).

Built from the drafts after a run. Pass rates are the grader's: of the items it graded, the share
graded above ``review_flag_threshold``, counted before its drops (R16). The book is promotable only
when every section is generated and graded, none failed, both pass rates reach the gate's
thresholds, and the grader's calibration for its current prompt and model is good enough.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from thinkbible_core.rules import max_questions
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
    min_strong_first_rate: float | None = None
    min_full_set_rate: float | None = None


# A section's first question is "strong" at this grade or above.
STRONG_FIRST_GRADE = 4


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
    # Every graded candidate question: information, not a bar (the writer over-produces on purpose).
    question_pass_rate: float | None = None
    # What readers get, per section with questions to ask (2026-11-19): a first question graded 4 or
    # 5, and as many questions as the section's key ideas allow (up to 3).
    strong_first: Rate = Field(default_factory=Rate)
    full_sets: Rate = Field(default_factory=Rate)
    strong_first_rate: float | None = None
    full_set_rate: float | None = None
    dropped_by_stage: dict[str, int] = Field(default_factory=dict)  # generate, check, review, …
    failed_sections: list[SectionIssue] = Field(default_factory=list)
    not_generated: list[str] = Field(default_factory=list)
    no_prompt: list[SectionIssue] = Field(default_factory=list)
    # Live items the grader now scores at or below the threshold: frozen, so only `retire
    # --replace` fixes them (FR-024a). Information, not a blocker.
    weak_live: list[SectionIssue] = Field(default_factory=list)
    calibration: Calibration | None = None
    thresholds: Thresholds | None = None
    promotable: bool = False
    promotable_reason: str = ""
    # The book introduction (on the first section's draft): why it is missing or failed, if so.
    introduction_problem: str | None = None
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
            min_strong_first_rate=settings.gate.min_strong_first_rate,
            min_full_set_rate=settings.gate.min_full_set_rate,
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
        for item_id in draft.live.items if draft.live is not None else {}:
            live_grade = draft.grades.get(item_id)
            if live_grade is not None and live_grade.score <= threshold:
                card.weak_live.append(
                    SectionIssue(
                        section_id=item_id,
                        reason=f"graded {live_grade.score}: {live_grade.notes}",
                    )
                )
        if not draft.failed and not section.get("noPrompt") and review and review.status == "done":
            _count_reader_measures(card, section, draft)
    card.graded = bool(sections) and not card.not_generated and ungraded == 0
    card.idea_pass_rate = card.ideas.pass_rate
    card.question_pass_rate = card.questions.pass_rate
    card.strong_first_rate = card.strong_first.pass_rate
    card.full_set_rate = card.full_sets.pass_rate

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
    card.introduction_problem = _introduction_problem(sections, drafts)
    card.blockers = _blockers(card, settings, ungraded)
    card.promotable = not card.blockers
    card.promotable_reason = "; ".join(card.blockers)
    return card


def _count_reader_measures(card: Scorecard, section: dict[str, Any], draft: SectionDraft) -> None:
    """A graded section's first question and question count, as readers will meet them."""
    questions = [q for q in section.get("questions", []) if q.get("status", "active") == "active"]
    ideas = [
        i
        for i in section.get("keyIdeas", [])
        if i.get("kind", "key") == "key" and i.get("status", "active") == "active"
    ]
    first = draft.grades.get(questions[0]["id"]) if questions else None
    card.strong_first.total += 1
    if first is not None and first.score >= STRONG_FIRST_GRADE:
        card.strong_first.passed += 1
    card.full_sets.total += 1
    if questions and len(questions) >= max_questions(len(ideas)):
        card.full_sets.passed += 1


def _introduction_problem(
    sections: list[SectionMapEntry], drafts: dict[str, SectionDraft]
) -> str | None:
    """Why the book has no usable introduction, or None (also None for a book whose
    commentators give no preface, and before the first section is generated)."""
    first = drafts.get(sections[0].id) if sections else None
    if first is None or "generate" not in first.stages:
        return None
    rec = first.stages.get("intro")
    if rec is None:
        return "not written yet: run the intro stage"
    if rec.status != "done":
        return rec.error or "the intro stage failed"
    if first.book_intro is not None and first.book_intro.problem:
        return first.book_intro.problem
    return None


def _blockers(card: Scorecard, settings: Settings, ungraded: int) -> list[str]:
    gate = settings.gate
    out = []
    if card.introduction_problem:
        out.append(f"book introduction: {card.introduction_problem}")
    if card.not_generated:
        out.append(f"{len(card.not_generated)} sections not generated")
    if ungraded:
        out.append(f"{ungraded} sections not graded")
    if card.failed_sections:
        out.append(f"{len(card.failed_sections)} sections failed")
    if card.idea_pass_rate is not None and card.idea_pass_rate < gate.min_idea_pass_rate:
        out.append(f"idea pass rate {card.idea_pass_rate:.2f} < {gate.min_idea_pass_rate:.2f}")
    if card.strong_first_rate is not None and card.strong_first_rate < gate.min_strong_first_rate:
        out.append(
            f"first questions graded 4 or 5: {card.strong_first_rate:.2f} < "
            f"{gate.min_strong_first_rate:.2f}"
        )
    if card.full_set_rate is not None and card.full_set_rate < gate.min_full_set_rate:
        out.append(
            f"sections with a full set of questions: {card.full_set_rate:.2f} < "
            f"{gate.min_full_set_rate:.2f}"
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
