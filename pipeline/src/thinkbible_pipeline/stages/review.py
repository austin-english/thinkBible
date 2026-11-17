"""The ``review`` stage (T062, R16): the quality gate's grader (Opus).

One call per section: the grader sees the passage (BSB and KJV), each commentator's notes (the same
excerpts ``generate`` was given) and every key idea and question, and grades each 1-5 against the
rubric in ``prompts/review/vN.md``, with the rubric lines it breaks and a short reason. Grades are
stored in ``grades``; items at or below ``review_flag_threshold`` are dropped. A section left
unusable (no key idea or no question) is regenerated once on the next run, then failed (FR-018).

``grade_items`` is shared with ``calibrate``, so the calibrated grader is exactly this one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.commentary.gather import gather_all
from thinkbible_pipeline.drafts.models import Grade, SectionDraft, SectionMapEntry
from thinkbible_pipeline.gate.checks import CheckContext, section_problems
from thinkbible_pipeline.gate.outcomes import clear_earlier_failure, drop_items, regenerate_or_fail
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


def stamp(draft: SectionDraft, stage: str) -> str | None:
    """Identifies the output of an earlier stage, so a later stage re-runs when it changes."""
    rec = draft.stages.get(stage)
    return f"{rec.status}:{rec.input_hash}@{rec.completed_at}" if rec else None


def _item_lines(section: dict[str, Any], items: list[dict[str, Any]], chapter: int) -> str:
    titles = {i["id"]: i["title"] for i in section.get("keyIdeas", [])}
    lines = []
    for item in items:
        verses = f"verses {item['verseStart']}-{item['verseEnd']}"
        if "targets" in item:  # a question
            aims = "; ".join(f"{t} ({titles.get(t, 'unknown idea')})" for t in item["targets"])
            lines.append(f"- {item['id']} [question; {verses}; aims at: "
                         f"{aims}]\n  {readable(item['text'], chapter)}")  # fmt: skip
        else:
            names = ", ".join(COMMENTATOR_NAMES.get(s, s) for s in item["sources"])
            lines.append(f"- {item['id']} [key idea; {verses}; sources: {names}]\n  "
                         f"{readable(item['title'], chapter)}: "
                         f"{readable(item['body'], chapter)}")  # fmt: skip
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
        g.item_id: ItemGrade(max(1, min(5, g.score)), g.reason.strip(), tuple(g.failed_rules))
        for g in out.items
        if g.item_id in wanted
    }
    return grades, usage


class ReviewStage(SectionStage):
    name = "review"

    def prompt_version(self, deps: Deps) -> str:
        return version_tag(system_prompt(self.name, deps.settings).versions)

    def model(self, deps: Deps) -> str:
        return deps.settings.stage(self.name).model

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        return {"generate": stamp(draft, "generate"), "check": stamp(draft, "check")}

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        rec = draft.stages.get("generate")
        section = draft.section
        items = [*section.get("keyIdeas", []), *section.get("questions", [])]
        if rec is None or rec.status != "done" or not items:
            return SectionResult()  # nothing generated, or nothing to grade
        entry = section_entry(section_id, deps)
        grades, usage = await grade_items(entry, section, items, deps)
        threshold = deps.settings.review_flag_threshold
        draft.grades = {
            item_id: Grade(
                score=g.score,
                notes=g.reason
                + (f" (breaks: {', '.join(g.failed_rules)})" if g.failed_rules else ""),
            )
            for item_id, g in grades.items()
        }
        drops = {
            item_id: f"graded {g.score}: {g.reason}"
            for item_id, g in grades.items()
            if g.score <= threshold
        }
        drop_items(draft, drops, "review")
        book = resolve_book(deps.store.book)
        problems = section_problems(draft.section, CheckContext.for_book(deps.sources, book.code))
        if problems:
            regenerate_or_fail(draft, deps.store, section_id, "review", problems[0])
        clear_earlier_failure(draft, "review")
        return SectionResult(usages=[usage])
