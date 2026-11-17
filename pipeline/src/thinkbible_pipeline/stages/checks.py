"""The ``check`` stage (T060, FR-016): the quality gate's rule checks on each finished section.

No model calls. ``generate`` already applies the item checks before it chooses a pool, so this
stage normally finds nothing to drop; it is the gate's verifier, and it applies checks added after
a section was generated:

1. Every key idea and question again (``gate/checks.py``), plus each idea's sources against its
   evidence quotes and each question's targets against the ideas kept. Failing items are dropped
   with ``stage: "check"``; questions above the level cap the remaining ideas allow are dropped;
   an alternate whose primary was dropped takes its place.
2. The section against the pack schema and the shared cross-field rules.

A section that breaks a rule here is flagged for regeneration: the next run's ``generate``
regenerates it once. If the regenerated content fails too, the section is marked failed (FR-018).
It re-runs only when ``generate`` produced new content or the checks change (``CHECKS_VERSION``).
"""

from __future__ import annotations

from typing import Any

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.drafts.models import CheckResult, DroppedItem, SectionDraft
from thinkbible_pipeline.gate.checks import (
    CHECKS_VERSION,
    CheckContext,
    idea_problem,
    question_problem,
    section_problems,
)
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage
from thinkbible_pipeline.stages.generate import SectionFailed


def _drop(item: dict[str, Any], reason: str) -> DroppedItem:
    return DroppedItem(item_id=item["id"], stage="check", reason=reason, item=item)


def apply_checks(draft: SectionDraft, ctx: CheckContext) -> list[str]:
    """Drop failing items from ``draft.section`` in place; return the section's problems."""
    section = draft.section
    dropped: list[DroppedItem] = []
    ideas = []
    for idea in section.get("keyIdeas", []):
        backed = {e.commentator for e in draft.evidence.get(idea["id"], [])}
        problem = idea_problem(idea["title"], idea["body"], ctx)
        if problem is None and not set(idea["sources"]) <= backed:
            problem = "evidence: a source has no quote found in that commentator's notes"
        if problem:
            dropped.append(_drop(idea, problem))
        else:
            ideas.append(idea)
    kept_ids = {i["id"] for i in ideas}
    texts = [(i["title"], i["body"]) for i in ideas]
    cap = min(3, len(ideas))
    questions = []
    for q in section.get("questions", []):
        targets = [t for t in q["targets"] if t in kept_ids]
        variants = list((q.get("textByTranslation") or {}).values())
        problem = next(
            (p for p in (question_problem(t, texts, ctx) for t in [q["text"], *variants]) if p),
            None,
        )
        if not targets:
            problem = "targets no key idea that was kept"
        elif q["level"] > cap:
            problem = (
                f"Level {q['level']} needs at least {q['level']} key ideas ({len(ideas)} left)"
            )
        if problem:
            dropped.append(_drop(q, problem))
        else:
            questions.append({**q, "targets": targets})
    for level in {q["level"] for q in questions}:  # an alternate stands in for a dropped primary
        at = [q for q in questions if q["level"] == level]
        if all(q["isAlternate"] for q in at):
            at[0]["isAlternate"] = False
    if dropped:
        draft.section = {**section, "keyIdeas": ideas, "questions": questions}
        draft.dropped += dropped
    return section_problems(draft.section, ctx)


class CheckStage(SectionStage):
    name = "check"

    def prompt_version(self, deps: Deps) -> str:
        return CHECKS_VERSION

    def model(self, deps: Deps) -> None:
        return None

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        rec = draft.stages.get("generate")
        return {"generate": f"{rec.input_hash}@{rec.completed_at}" if rec else None}

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        rec = draft.stages.get("generate")
        if rec is None or rec.status != "done":
            return SectionResult()  # nothing generated to check
        book = resolve_book(deps.store.book)
        problems = apply_checks(draft, CheckContext.for_book(deps.sources, book.code))
        draft.checks = [
            CheckResult(item_id=section_id, check="section", ok=False, detail=p) for p in problems
        ] or [CheckResult(item_id=section_id, check="section", ok=True)]
        if problems:
            reason = f"checks: {problems[0]}"
            if draft.regenerated_for:
                draft.failed = f"{reason} (after one regeneration)"
            else:
                draft.regenerate = reason
                draft.failed = f"{reason} (regenerates on the next run)"
            deps.store.write_draft(section_id, draft)
            raise SectionFailed(f"{section_id}: {draft.failed}")
        if draft.failed and draft.failed.startswith("checks:"):  # an earlier check failure
            draft.failed, draft.regenerate = None, None
        return SectionResult()
