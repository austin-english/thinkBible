"""What the quality gate does with its findings (R11, R16, FR-018), shared by ``check`` and
``review``.

- ``drop_items``: removes the items a gate stage failed, and with them anything that no longer
  stands: a question whose target ideas are all gone, and the last questions when there are more
  than the kept ideas allow (one per idea, at most 3). The rest keep their order. Every removal is
  recorded with the stage and a reason.
- ``regenerate_or_fail``: a section the gate left unusable (no key idea, no question) is flagged
  for regeneration; the next run's ``generate`` regenerates it once, and if the new content fails
  too, the section is failed.
"""

from __future__ import annotations

from typing import Any, NoReturn

from thinkbible_core.rules import max_questions
from thinkbible_pipeline.drafts.models import DroppedItem, SectionDraft
from thinkbible_pipeline.drafts.store import DraftStore

GateStage = str  # "check", "review"


class SectionFailed(RuntimeError):
    """The section broke a rule it can't recover from in this run. Its draft is saved first."""


def _drop(item: dict[str, Any], stage: GateStage, reason: str) -> DroppedItem:
    return DroppedItem(item_id=item["id"], stage=stage, reason=reason, item=item)  # type: ignore[arg-type]


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
    cap = max_questions(len(ideas))
    questions: list[dict[str, Any]] = []
    for q in section.get("questions", []):
        targets = [t for t in q["targets"] if t in kept_ids]
        if q["id"] in drops:
            dropped.append(_drop(q, stage, drops[q["id"]]))
        elif not targets:
            dropped.append(_drop(q, stage, "targets no key idea that was kept"))
        elif len(questions) >= cap:
            reason = f"more than {cap} questions for the {len(ideas)} key ideas left"
            dropped.append(_drop(q, stage, reason))
        else:
            questions.append({**q, "targets": targets})
    if dropped:
        draft.section = {**section, "keyIdeas": ideas, "questions": questions}
        draft.dropped += dropped


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
