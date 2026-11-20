"""The ``review`` stage (T062, R16): the quality gate's grader (Opus).

One call per section: the grader sees the passage (BSB and KJV), each commentator's notes (the same
excerpts ``generate`` was given), every key idea and every candidate question, and grades each 1-5
against the rubric in ``prompts/review/vN.md``, with the rubric lines it breaks and a short reason.
Grades are stored in ``grades``. Key ideas at or below ``review_flag_threshold`` are dropped. Of the
candidate questions above it, the best graded are kept (up to 3, one per key idea first), in the
writer's order; the rest are recorded as not chosen (R11, 2026-11-17). A section left unusable (no
key idea or no question) is regenerated once on the next run, then failed (FR-018).

``grade_items`` is shared with ``calibrate``, so the calibrated grader is exactly this one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from thinkbible_core.ids import resolve_book
from thinkbible_core.rules import max_questions
from thinkbible_pipeline.commentary.gather import gather_all
from thinkbible_pipeline.drafts.live import is_live, live_ids
from thinkbible_pipeline.drafts.models import DroppedItem, Grade, SectionDraft, SectionMapEntry
from thinkbible_pipeline.gate.checks import CheckContext, section_problems
from thinkbible_pipeline.gate.outcomes import (
    clear_earlier_failure,
    drop_items,
    pick_best,
    pick_opener,
    regenerate_or_fail,
)
from thinkbible_pipeline.llm.outputs import ReviewOut
from thinkbible_pipeline.llm.prompts import system_prompt, version_tag
from thinkbible_pipeline.llm.runner import Usage
from thinkbible_pipeline.report.render import readable
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage
from thinkbible_pipeline.stages.generate import COMMENTATOR_NAMES, _commentary, _header, _passages
from thinkbible_pipeline.stages.summaries import section_entry


@dataclass(frozen=True)
class ItemGrade:
    score: int
    reason: str
    failed_rules: tuple[str, ...]
    focus: str | None = None  # questions: "big-picture" or "detail"


def stamp(draft: SectionDraft, stage: str) -> str | None:
    """Identifies the output of an earlier stage, so a later stage re-runs when it changes."""
    rec = draft.stages.get(stage)
    return f"{rec.status}:{rec.input_hash}@{rec.completed_at}" if rec else None


def _item_lines(section: dict[str, Any], items: list[dict[str, Any]], chapter: int) -> str:
    titles = {i["id"]: i["title"] for i in section.get("keyIdeas", [])}
    lines = []
    for item in items:
        if "note" in item:  # the context or views-differ note
            lines.append(
                f"- {item['id']} [{item['note']} note]\n  {readable(item['text'], chapter)}"
            )
            continue
        verses = f"verses {item['verseStart']}-{item['verseEnd']}"
        if "targets" in item:  # a question
            aims = "; ".join(f"{t} ({titles.get(t, 'unknown idea')})" for t in item["targets"])
            lines.append(f"- {item['id']} [question; {verses}; aims at: "
                         f"{aims}]\n  {readable(item['text'], chapter)}")  # fmt: skip
        else:
            names = ", ".join(COMMENTATOR_NAMES.get(s, s) for s in item["sources"])
            kind = "background idea" if item.get("kind") == "background" else "key idea"
            quotes = "".join(
                f"\n  In their words ({COMMENTATOR_NAMES.get(q['commentator'], q['commentator'])})"
                f": '{q['text']}'"
                for q in item.get("quotes", [])
            )
            lines.append(f"- {item['id']} [{kind}; {verses}; sources: {names}]\n  "
                         f"{readable(item['title'], chapter)}: "
                         f"{readable(item['body'], chapter)}{quotes}")  # fmt: skip
    return "\n".join(lines)


async def grade_items(
    entry: SectionMapEntry,
    section: dict[str, Any],
    items: list[dict[str, Any]],
    deps: Deps,
) -> tuple[dict[str, ItemGrade], Usage]:
    """The grader's grade for each of ``items`` (key ideas and questions of ``entry``)."""
    book = resolve_book(deps.store.book)
    excerpts = gather_all(
        entry, book.code, deps.sources, cap_tokens=deps.settings.excerpt_cap_tokens
    )
    user = (
        f"{_header(entry.id, entry, book.name)}\n\n{_passages(deps, book.code, entry)}\n\n"
        f"{_commentary(excerpts)}\n\nItems to grade:\n{_item_lines(section, items, entry.chapter)}"
    )
    out, usage = await deps.runner.parse(
        "review",
        system_prompt("review", deps.settings).blocks,
        user,
        ReviewOut,
        section_id=entry.id,
    )
    wanted = {i["id"] for i in items}
    grades = {
        g.item_id: ItemGrade(
            max(1, min(5, g.score)), g.reason.strip(), tuple(g.failed_rules), g.focus
        )
        for g in out.items
        if g.item_id in wanted
    }
    return grades, usage


# A big-picture question leads only if the grader gives it at least this.
BIG_PICTURE_MIN_SCORE = 4


def order_questions(
    kept: list[dict[str, Any]],
    grades: dict[str, ItemGrade],
    scores: dict[str, int],
    central: str | None,
) -> list[dict[str, Any]]:
    """The kept questions in the order readers meet them (2026-11-19).

    First, a question the grader marked big-picture and graded 4 or more: the best-graded, then
    one on the central idea. Without one, the best-graded question, with the central idea only
    breaking ties, then the one spanning most of the passage. The rest keep the writer's order.
    (Mark 1:16-20 had led with "leave everything", a 4 on the central idea, ahead of the big-picture
    "Why might he start with men like these?", a 5; in 12 of Mark's sections with no big-picture
    question, a detail 4 on the central idea had led ahead of a 5.)
    """
    if not kept:
        return kept
    big = [
        c
        for c in kept
        if (g := grades.get(c["id"])) is not None
        and g.focus == "big-picture"
        and g.score >= BIG_PICTURE_MIN_SCORE
    ]
    first = max(
        big or kept,
        key=lambda c: (
            scores.get(c["id"], 0),
            central is not None and central in c["targets"],
            0 if big else c["verseEnd"] - c["verseStart"],
            -kept.index(c),
        ),
    )
    return [first, *(c for c in kept if c is not first)]


# Bump when the rules for keeping and ordering questions change (choose_questions, pick_opener,
# pick_best, order_questions): every section's review runs again, reusing its stored grades.
SELECTION_RULES = "2026-11-19: big-picture ties; best-graded first without big-picture"


def choose_questions(
    draft: SectionDraft,
    candidates: list[dict[str, Any]],
    grades: dict[str, ItemGrade],
    threshold: int,
) -> None:
    """Keep the best-graded candidates as the section's questions; record why the rest went."""
    kept_ideas = {
        i["id"] for i in draft.section.get("keyIdeas", []) if i.get("kind", "key") == "key"
    }
    eligible: list[dict[str, Any]] = []
    dropped: list[DroppedItem] = []

    def drop(c: dict[str, Any], reason: str) -> None:
        dropped.append(DroppedItem(item_id=c["id"], stage="review", reason=reason, item=c))

    for c in candidates:
        g = grades.get(c["id"])
        targets = [t for t in c["targets"] if t in kept_ideas]
        if g is not None and g.score <= threshold:
            drop(c, f"graded {g.score}: {g.reason}")
        elif not targets:
            drop(c, "targets no key idea that was kept")
        else:
            eligible.append({**c, "targets": targets})
    scores = {cid: g.score for cid, g in grades.items()}
    start, end = draft.section["verseStart"], draft.section["verseEnd"]
    cap = max_questions(len(kept_ideas))
    central = draft.central_idea if draft.central_idea in kept_ideas else None
    # One place goes to the best question on the central idea if it grades 4 or more; the others
    # stay quality first. Equal grades prefer what the grader marked big-picture.
    big = {cid for cid, g in grades.items() if g.focus == "big-picture"}
    opener = pick_opener(eligible, scores, central, start, end, big) if cap else None
    rest = [c for c in eligible if c is not opener]
    picked = set(
        pick_best(rest, scores, cap - (opener is not None), start, end,
                  covered=set(opener["targets"]) if opener else None, big=big)
    )  # fmt: skip
    if opener is not None:
        picked.add(opener["id"])
    kept = order_questions([c for c in eligible if c["id"] in picked], grades, scores, central)
    for c in eligible:
        if c["id"] not in picked:
            score = scores.get(c["id"])
            graded = f"graded {score}" if score is not None else "not graded"
            drop(c, f"not chosen: {graded}; better-graded questions were kept")
    draft.section = {**draft.section, "questions": kept}
    draft.dropped += dropped


def choose_live_questions(
    draft: SectionDraft,
    candidates: list[dict[str, Any]],
    grades: dict[str, ItemGrade],
    threshold: int,
) -> None:
    """A live section (FR-024a): its questions stay as they are; new ones only fill free places.

    Live questions, and any the owner added by ``retire --replace``, keep their order. New
    candidates (from ``--refresh``) graded above ``threshold`` and aimed at an active key idea fill
    the places left under the cap, quality first, after the existing ones.
    """
    frozen = live_ids(draft)
    cand_ids = {c["id"] for c in candidates}
    keep = [
        q
        for q in draft.section.get("questions", [])
        if q["id"] in frozen or q["id"] not in cand_ids
    ]
    ideas = {
        i["id"]
        for i in draft.section.get("keyIdeas", [])
        if i.get("kind", "key") == "key" and i.get("status", "active") == "active"
    }
    active = sum(1 for q in keep if q.get("status", "active") == "active")
    free = max(0, max_questions(len(ideas)) - active)
    scores = {cid: g.score for cid, g in grades.items()}
    eligible = []
    for c in candidates:
        if c["id"] in frozen or c["id"] in {q["id"] for q in keep}:
            continue
        g = grades.get(c["id"])
        targets = [t for t in c["targets"] if t in ideas]
        if g is not None and g.score > threshold and targets:
            eligible.append({**c, "targets": targets})
    start, end = draft.section["verseStart"], draft.section["verseEnd"]
    big = {cid for cid, g in grades.items() if g.focus == "big-picture"}
    picked = set(pick_best(eligible, scores, free, start, end, big=big)) if free else set()
    draft.section = {
        **draft.section,
        "questions": [*keep, *(c for c in eligible if c["id"] in picked)],
    }


def note_items(section_id: str, section: dict[str, Any]) -> list[dict[str, Any]]:
    """The context and views-differ notes as items for the grader (readers see both)."""
    items = [{"id": f"{section_id}-context", "note": "context", "text": section.get("context", "")}]
    if section.get("viewsDiffer"):
        items.append(
            {"id": f"{section_id}-views", "note": "views-differ", "text": section["viewsDiffer"]}
        )
    return items


def judge_notes(
    draft: SectionDraft,
    section_id: str,
    notes: list[dict[str, Any]],
    grades: dict[str, ItemGrade],
    threshold: int,
) -> str | None:
    """A weak views-differ note is removed; a weak context note is a problem for the section."""
    problem = None
    for note in notes:
        g = grades.get(note["id"])
        if g is None or g.score > threshold:
            continue
        if note["note"] == "views-differ":
            draft.section = {**draft.section, "viewsDiffer": None}
            draft.dropped.append(
                DroppedItem(
                    item_id=note["id"],
                    stage="review",
                    reason=f"graded {g.score}: {g.reason}",
                    item={"viewsDiffer": note["text"]},
                )
            )
        else:
            problem = f"the context note graded {g.score}: {g.reason}"
    return problem


class ReviewStage(SectionStage):
    name = "review"

    def prompt_version(self, deps: Deps) -> str:
        return version_tag(system_prompt(self.name, deps.settings).versions)

    def model(self, deps: Deps) -> str:
        return deps.settings.stage(self.name).model

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        return {
            "generate": stamp(draft, "generate"),
            "check": stamp(draft, "check"),
            # A change to the rules for keeping and ordering questions re-runs this stage; it
            # reuses the section's stored grades when the grader is unchanged (no model call).
            "selection": SELECTION_RULES,
        }

    def costs_nothing(self, section_id: str, draft: SectionDraft, deps: Deps) -> bool:
        candidates = draft.candidates or draft.section.get("questions", [])
        return self._stored_grades(draft, candidates, deps) is not None

    def _stored_grades(
        self, draft: SectionDraft, candidates: list[dict[str, Any]], deps: Deps
    ) -> dict[str, ItemGrade] | None:
        """The section's grades from its last review, if that review used this grader and graded
        these same candidate questions (new content has new IDs); then only the selection runs
        again."""
        prev = draft.stages.get("review")
        if (
            prev is None
            or prev.status != "done"
            or prev.prompt_version != self.prompt_version(deps)
            or prev.model != self.model(deps)
            or not candidates
            or not all(c["id"] in draft.grades for c in candidates)
        ):
            return None
        return {
            item_id: ItemGrade(g.score, g.notes or "", (), g.focus)
            for item_id, g in draft.grades.items()
        }

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        rec = draft.stages.get("generate")
        section = draft.section
        ideas = section.get("keyIdeas", [])
        # Drafts from before 2026-11-17 have no candidates: their questions are the candidates.
        candidates = draft.candidates or section.get("questions", [])
        notes = note_items(section_id, section)
        items = [*ideas, *candidates, *notes]
        if rec is None or rec.status != "done" or not items:
            return SectionResult()  # nothing generated, or nothing to grade
        entry = section_entry(section_id, deps)
        stored = self._stored_grades(draft, candidates, deps)
        if stored is not None:
            grades, usages = stored, []
        else:
            grades, usage = await grade_items(entry, section, items, deps)
            usages = [usage]
        threshold = deps.settings.review_flag_threshold
        draft.grades = {
            item_id: Grade(
                score=g.score,
                notes=g.reason
                + (f" (breaks: {', '.join(g.failed_rules)})" if g.failed_rules else ""),
                focus=g.focus,
            )
            for item_id, g in grades.items()
        }
        if is_live(draft):
            # Live (FR-024a): grades go to the scorecard; nothing live is dropped or re-picked.
            choose_live_questions(draft, candidates, grades, threshold)
            clear_earlier_failure(draft, "review")
            return SectionResult(usages=usages)
        # A re-run (say, a new rubric) chooses again from all the candidates.
        cand_ids = {c["id"] for c in candidates}
        draft.dropped = [
            d for d in draft.dropped if not (d.stage == "review" and d.item_id in cand_ids)
        ]
        idea_drops = {
            i["id"]: f"graded {g.score}: {g.reason}"
            for i in ideas
            if (g := grades.get(i["id"])) is not None and g.score <= threshold
        }
        draft.section = {**section, "questions": []}
        drop_items(draft, idea_drops, "review")
        choose_questions(draft, candidates, grades, threshold)
        context_problem = judge_notes(draft, section_id, notes, grades, threshold)
        book = resolve_book(deps.store.book)
        problems = section_problems(draft.section, CheckContext.for_book(deps.sources, book.code))
        if context_problem:
            problems.insert(0, context_problem)
        if problems:
            regenerate_or_fail(draft, deps.store, section_id, "review", problems[0])
        clear_earlier_failure(draft, "review")
        return SectionResult(usages=usages)
