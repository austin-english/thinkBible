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


# The central idea's best question opens the section only if the grader gives it at least this.
OPENER_MIN_SCORE = 4


def is_big_picture(question: dict[str, Any], start: int, end: int) -> bool:
    """Whether a question is about at least half of the passage (verses ``start``-``end``)."""
    if (question["verseStart"], question["verseEnd"]) == (start, end):
        return True
    span = int(question["verseEnd"]) - int(question["verseStart"]) + 1
    return span >= 2 and span * 2 >= end - start + 1


def pick_opener(
    candidates: list[dict[str, Any]],
    scores: dict[str, int],
    central: str | None,
    start: int,
    end: int,
    big: frozenset[str] | set[str] = frozenset(),
) -> dict[str, Any] | None:
    """The question kept for the central idea: the best-graded one on it, if it grades at least
    ``OPENER_MIN_SCORE`` (2026-11-18). Ties go to one the grader marked big-picture (``big``,
    2026-11-19), then one about at least half the passage, then the writer's order. None when
    there is no such question: the picks then run as before.
    """
    on_central = [
        (n, c)
        for n, c in enumerate(candidates)
        if central in c["targets"] and scores.get(c["id"], 0) >= OPENER_MIN_SCORE
    ]
    if central is None or not on_central:
        return None
    _, best = min(
        on_central,
        key=lambda nc: (
            -scores[nc[1]["id"]],
            nc[1]["id"] not in big,
            not is_big_picture(nc[1], start, end),
            nc[0],
        ),
    )
    return best


def pick_best(
    candidates: list[dict[str, Any]],
    scores: dict[str, int],
    cap: int,
    start: int,
    end: int,
    covered: set[str] | None = None,
    big: frozenset[str] | set[str] = frozenset(),
) -> list[str]:
    """The IDs of up to ``cap`` candidates, returned in the writer's order.

    Quality first (revised 2026-11-17): each place goes to the highest-graded candidate left, so a
    lower grade never beats a higher one. Among equal grades, prefer one aimed at a key idea the
    picks so far (and ``covered``) don't cover, then one the grader marked big-picture (``big``;
    2026-11-19: Mark 3:1-6 dropped "Why might a clear act of mercy lead to a plot rather than
    belief?", a big-picture 5, for two detail 5s on the writer's order), then one aimed at a
    better-graded idea (2026-11-19: Mark 1:1-11 kept a question on an idea graded 3 over one on an
    idea graded 5), then one about at least half the passage, then the writer's order.
    (Covering every idea first had kept a 3 over a 5, and a reserved place for a whole-passage
    question had let broad questions beat sharper ones; Mark 1:21-28.)
    """

    def rank(n: int, covered: set[str]) -> tuple[int, bool, bool, int, bool, int]:
        c = candidates[n]
        return (
            -scores.get(c["id"], 0),
            not (set(c["targets"]) - covered),
            c["id"] not in big,
            -max((scores.get(t, 0) for t in c["targets"]), default=0),
            not is_big_picture(c, start, end),
            n,
        )

    chosen: list[int] = []
    covered = set(covered or ())
    remaining = list(range(len(candidates)))
    while remaining and len(chosen) < cap:
        best = min(remaining, key=lambda n: rank(n, covered))
        chosen.append(best)
        remaining.remove(best)
        covered |= set(candidates[best]["targets"])
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
