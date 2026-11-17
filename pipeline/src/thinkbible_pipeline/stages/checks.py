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
from thinkbible_pipeline.drafts.models import CheckResult, SectionDraft
from thinkbible_pipeline.gate.checks import (
    CHECKS_VERSION,
    CheckContext,
    idea_problem,
    question_problem,
    section_problems,
)
from thinkbible_pipeline.gate.outcomes import clear_earlier_failure, drop_items, regenerate_or_fail
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage


def apply_checks(draft: SectionDraft, ctx: CheckContext) -> list[str]:
    """Drop failing items from ``draft.section`` in place; return the section's problems."""
    section = draft.section
    drops: dict[str, str] = {}
    texts = []
    for idea in section.get("keyIdeas", []):
        backed = {e.commentator for e in draft.evidence.get(idea["id"], [])}
        problem = idea_problem(idea["title"], idea["body"], ctx)
        if problem is None and not set(idea["sources"]) <= backed:
            problem = "evidence: a source has no quote found in that commentator's notes"
        if problem:
            drops[idea["id"]] = problem
        else:
            texts.append((idea["title"], idea["body"]))
    for q in section.get("questions", []):
        variants = list((q.get("textByTranslation") or {}).values())
        problem = next(
            (p for p in (question_problem(t, texts, ctx) for t in [q["text"], *variants]) if p),
            None,
        )
        if problem:
            drops[q["id"]] = problem
    drop_items(draft, drops, "check")
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
            regenerate_or_fail(draft, deps.store, section_id, "check", problems[0])
        clear_earlier_failure(draft, "check")
        return SectionResult()
