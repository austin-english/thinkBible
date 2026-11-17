"""What the quality gate does with its findings (R11, R16, FR-018), shared by ``check``,
``review`` and ``levels``.

- ``drop_items``: removes the items a gate stage failed, and with them anything that no longer
  stands: a question whose target ideas are all gone, a question above the level cap the remaining
  ideas allow. Then each level is re-picked: a primary and at most one alternate, an alternate
  stepping in for a dropped primary. Every removal is recorded with the stage and a reason.
- ``regenerate_or_fail``: a section the gate left unusable (no key idea, no Level 1 question, a
  missing level, no whole-passage question) is flagged for regeneration; the next run's
  ``generate`` regenerates it once, and if the new content fails too, the section is failed.
"""

from __future__ import annotations

from typing import Any, NoReturn

from thinkbible_pipeline.drafts.models import DroppedItem, SectionDraft
from thinkbible_pipeline.drafts.store import DraftStore

GateStage = str  # "check", "review", "levels"
MAX_PER_LEVEL = 2


class SectionFailed(RuntimeError):
    """The section broke a rule it can't recover from in this run. Its draft is saved first."""


def _drop(item: dict[str, Any], stage: GateStage, reason: str) -> DroppedItem:
    return DroppedItem(item_id=item["id"], stage=stage, reason=reason, item=item)  # type: ignore[arg-type]


def repool(questions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Per level, keep a primary and at most one alternate (existing primaries first).

    Returns (kept, overflow). An alternate becomes the primary when its level has none.
    """
    kept: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    for level in sorted({q["level"] for q in questions}):
        at = sorted((q for q in questions if q["level"] == level), key=lambda q: q["isAlternate"])
        for n, q in enumerate(at):
            if n < MAX_PER_LEVEL:
                kept.append({**q, "isAlternate": n > 0})
            else:
                overflow.append(q)
    return kept, overflow


def drop_items(draft: SectionDraft, drops: dict[str, str], stage: GateStage) -> None:
    """Drop the items in ``drops`` ({item id: reason}) and whatever no longer stands without."""
    section = draft.section
    dropped: list[DroppedItem] = []
    ideas = []
    for idea in section.get("keyIdeas", []):
        if idea["id"] in drops:
            dropped.append(_drop(idea, stage, drops[idea["id"]]))
        else:
            ideas.append(idea)
    kept_ids = {i["id"] for i in ideas}
    cap = min(3, len(ideas))
    survivors = []
    for q in section.get("questions", []):
        targets = [t for t in q["targets"] if t in kept_ids]
        if q["id"] in drops:
            dropped.append(_drop(q, stage, drops[q["id"]]))
        elif not targets:
            dropped.append(_drop(q, stage, "targets no key idea that was kept"))
        elif q["level"] > cap:
            reason = f"Level {q['level']} needs at least {q['level']} key ideas ({len(ideas)} left)"
            dropped.append(_drop(q, stage, reason))
        else:
            survivors.append({**q, "targets": targets})
    questions, overflow = repool(survivors)
    dropped += [
        _drop(q, stage, f"Level {q['level']} already has {MAX_PER_LEVEL} questions")
        for q in overflow
    ]
    if dropped:
        draft.section = {**section, "keyIdeas": ideas, "questions": questions}
        draft.dropped += dropped
    elif questions != section.get("questions", []):  # a level change re-picked the pool
        draft.section = {**section, "questions": questions}


def regenerate_or_fail(
    draft: SectionDraft, store: DraftStore, section_id: str, stage: GateStage, problem: str
) -> NoReturn:
    reason = f"{stage}: {problem}"
    if draft.regenerated_for:
        draft.failed = f"{reason} (after one regeneration)"
    else:
        draft.regenerate = reason
        draft.failed = f"{reason} (regenerates on the next run)"
    store.write_draft(section_id, draft)
    raise SectionFailed(f"{section_id}: {draft.failed}")


def clear_earlier_failure(draft: SectionDraft, stage: GateStage) -> None:
    """A section that now passes ``stage`` sheds that stage's earlier failure."""
    if draft.failed and draft.failed.startswith(f"{stage}:"):
        draft.failed, draft.regenerate = None, None
