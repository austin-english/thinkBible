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
    kept_ids = {i["id"] for i in ideas if i.get("kind", "key") == "key"}  # questions aim at these
    cap = max_questions(len(kept_ids))
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


OPENER_MIN_SCORE = 4  # a big-picture opener must still be a good question


def is_big_picture(question: dict[str, Any], start: int, end: int) -> bool:
    """Whether a question is about at least half of the passage (verses ``start``-``end``)."""
    if (question["verseStart"], question["verseEnd"]) == (start, end):
        return True
    span = int(question["verseEnd"]) - int(question["verseStart"]) + 1
    return span >= 2 and span * 2 >= end - start + 1


def pick_opener(
    candidates: list[dict[str, Any]], scores: dict[str, int], start: int, end: int
) -> str | None:
    """The best-graded big-picture candidate scoring at least ``OPENER_MIN_SCORE``, or None.

    The first question a reader meets should open the passage's main idea; the grader on its own
    tends to prefer sharp one-verse questions (Mark 1:1-11 lost all three of its arc questions).
    """
    wide = [
        (n, c)
        for n, c in enumerate(candidates)
        if is_big_picture(c, start, end) and scores.get(c["id"], 0) >= OPENER_MIN_SCORE
    ]
    if not wide:
        return None
    _, best = min(wide, key=lambda nc: (-scores.get(nc[1]["id"], 0), nc[0]))
    return str(best["id"])


def pick_best(
    candidates: list[dict[str, Any]],
    scores: dict[str, int],
    cap: int,
    opener: str | None = None,
) -> list[str]:
    """The IDs of up to ``cap`` candidates, best graded first, then returned in the writer's order.

    ``opener``, if given, takes the first place. Each other pick first goes to the best-graded
    candidate aimed at a key idea the picks so far don't cover; remaining places go to the best
    graded of the rest. Ties keep the writer's order.
    """
    ranked = sorted(range(len(candidates)), key=lambda n: (-scores.get(candidates[n]["id"], 0), n))
    chosen: list[int] = []
    covered: set[str] = set()
    if opener is not None and cap > 0:
        first = next(n for n, c in enumerate(candidates) if c["id"] == opener)
        chosen.append(first)
        covered |= set(candidates[first]["targets"])
    for n in ranked:
        targets = set(candidates[n]["targets"])
        if len(chosen) < cap and targets - covered:
            chosen.append(n)
            covered |= targets
    for n in ranked:
        if len(chosen) < cap and n not in chosen:
            chosen.append(n)
    return [candidates[n]["id"] for n in sorted(chosen)]


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
