"""The ``levels`` stage (T063, R11): check each question's level against a typical reader (Haiku).

Two calls per section, not two per question:
1. ``levels-answer``: a typical reader answers every active question using only the passage.
2. ``levels-judge``: for each answer, which of the question's target ideas it reaches.

Then: a Level 3 question whose answer reaches all its targets is moved to Level 2 (too easy for
Level 3); a Level 1 question whose answer reaches none of them is dropped (too hard for a first
question), and its alternate steps in. Moves are recorded in ``levelChanges``. A section left
without a level it needs is regenerated once on the next run, then failed (FR-018).
"""

from __future__ import annotations

from typing import Any

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.drafts.models import LevelChange, SectionDraft
from thinkbible_pipeline.gate.checks import CheckContext, section_problems
from thinkbible_pipeline.gate.outcomes import clear_earlier_failure, drop_items, regenerate_or_fail
from thinkbible_pipeline.llm.outputs import LevelsAnswerOut, LevelsJudgeOut
from thinkbible_pipeline.llm.prompts import system_prompt, version_tag
from thinkbible_pipeline.report.render import readable
from thinkbible_pipeline.sections.passage import passage_text
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage
from thinkbible_pipeline.stages.generate import _header
from thinkbible_pipeline.stages.review import stamp
from thinkbible_pipeline.stages.summaries import section_entry

TOO_EASY = "a typical reader answered it fully from the passage: too easy for Level 3"
TOO_HARD = "a typical reader's answer reached none of its key ideas: too hard for Level 1"


class LevelsStage(SectionStage):
    name = "levels"

    def _prompts(self, deps: Deps) -> tuple[Any, Any]:
        return (
            system_prompt(self.name, deps.settings, prompt="levels-answer"),
            system_prompt(self.name, deps.settings, prompt="levels-judge"),
        )

    def prompt_version(self, deps: Deps) -> str:
        answer, judge = self._prompts(deps)
        return version_tag({**answer.versions, **judge.versions})

    def model(self, deps: Deps) -> str:
        return deps.settings.stage(self.name).model

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        return {s: stamp(draft, s) for s in ("generate", "check", "review")}

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        section = draft.section
        questions = section.get("questions", [])
        if not questions:
            return SectionResult()
        entry = section_entry(section_id, deps)
        book = resolve_book(deps.store.book)
        ch = entry.chapter
        answer_prompt, judge_prompt = self._prompts(deps)
        header = _header(section_id, entry, book.name)

        asked = "\n".join(f"- {q['id']}: {readable(q['text'], ch)}" for q in questions)
        answers_out, answer_usage = await deps.runner.parse(
            self.name, answer_prompt.blocks,
            f"{header}\n\n<passage>\n{passage_text(deps.sources, 'bsb', book.code, entry)}\n"
            f"</passage>\n\nQuestions:\n{asked}",
            LevelsAnswerOut, section_id=section_id, call="answer",
        )  # fmt: skip
        answers = {a.question_id: a.answer for a in answers_out.answers}

        ideas = {i["id"]: i for i in section.get("keyIdeas", [])}
        blocks = []
        for q in questions:
            targets = "\n".join(
                f"  - {t}: {readable(ideas[t]['title'], ch)}: {readable(ideas[t]['body'], ch)}"
                for t in q["targets"]
                if t in ideas
            )
            blocks.append(f"Question {q['id']}: {readable(q['text'], ch)}\n"
                          f"Answer: {answers.get(q['id'], '(no answer)')}\n"
                          f"Target key ideas:\n{targets}")  # fmt: skip
        judge_out, judge_usage = await deps.runner.parse(
            self.name, judge_prompt.blocks, f"{header}\n\n" + "\n\n".join(blocks),
            LevelsJudgeOut, section_id=section_id, call="judge",
        )  # fmt: skip
        covered = {j.question_id: set(j.covered_target_ids) for j in judge_out.judgments}

        changes: list[LevelChange] = []
        drops: dict[str, str] = {}
        moved = []
        for q in questions:
            if q["id"] not in covered:
                moved.append(q)  # not judged: leave it as it is
                continue
            reached = covered[q["id"]] & set(q["targets"])
            if q["level"] == 3 and reached == set(q["targets"]):
                changes.append(
                    LevelChange.model_validate(
                        {"questionId": q["id"], "from": 3, "to": 2, "reason": TOO_EASY}
                    )
                )
                moved.append({**q, "level": 2, "isAlternate": True})
            elif q["level"] == 1 and not reached:
                drops[q["id"]] = TOO_HARD
                moved.append(q)
            else:
                moved.append(q)
        draft.level_changes = changes
        draft.section = {**section, "questions": moved}
        drop_items(draft, drops, "levels")
        problems = section_problems(draft.section, CheckContext.for_book(deps.sources, book.code))
        if problems:
            regenerate_or_fail(draft, deps.store, section_id, "levels", problems[0])
        clear_earlier_failure(draft, "levels")
        return SectionResult(usages=[answer_usage, judge_usage])
