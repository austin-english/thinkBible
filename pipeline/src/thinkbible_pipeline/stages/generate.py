"""The ``generate`` stage (T054): key ideas, context and questions for one section (Sonnet).

Per section:

1. Gather each commentator's excerpt (``commentary/gather.py``) and record what was given.
2. Call 1, ``extract``: key ideas with evidence quotes, a context note, a views-differ note, or
   ``noPrompt`` when the commentators give nothing a question could target.
3. Keep only grounded ideas (``generate_rules.process_ideas``); if none survive, extract once more.
4. Unless ``noPrompt``, call 2, ``questions`` (with the question guide), given the passage, the
   commentators' notes and the kept ideas: up to 8 candidates in reading order. All that pass the
   checks are kept for the grader, which picks the best 3 in ``review``
   (``generate_rules.process_questions``). With no usable question the questions are regenerated
   once, with the problem named; then the section fails (FR-018).
5. Write the section: it replaces the previous machine output. IDs are never reused.
"""

from __future__ import annotations

from typing import Any

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.commentary.gather import COMMENTATORS, Excerpt, gather_all
from thinkbible_pipeline.drafts.models import DroppedItem, SectionDraft, SectionMapEntry
from thinkbible_pipeline.gate.checks import CheckContext
from thinkbible_pipeline.gate.outcomes import SectionFailed
from thinkbible_pipeline.jsonio import sha256_hex
from thinkbible_pipeline.llm.outputs import IdeasOut, QuestionsOut
from thinkbible_pipeline.llm.prompts import system_prompt, version_tag
from thinkbible_pipeline.llm.runner import Usage
from thinkbible_pipeline.sections.passage import passage_text
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage
from thinkbible_pipeline.stages.generate_rules import (
    Idea,
    QuestionPool,
    note_problem,
    process_ideas,
    process_questions,
)
from thinkbible_pipeline.stages.summaries import reference, section_entry

COMMENTATOR_NAMES = {
    "matthew-henry": "Matthew Henry",
    "jamieson-fausset-brown": "Jamieson-Fausset-Brown",
    "adam-clarke": "Adam Clarke",
}


def _previous_summary(section_id: str, deps: Deps) -> str | None:
    ids = deps.store.section_ids()
    i = ids.index(section_id) if section_id in ids else 0
    return deps.store.read_draft_or_new(ids[i - 1]).summary if i > 0 else None


def _header(section_id: str, entry: SectionMapEntry, book_name: str) -> str:
    return f'Section {section_id}: {reference(book_name, entry)}, "{entry.title}"'


def _passages(deps: Deps, book: str, entry: SectionMapEntry) -> str:
    return "\n\n".join(
        f'<passage translation="{t.upper()}">\n{passage_text(deps.sources, t, book, entry)}\n'
        "</passage>"
        for t in ("bsb", "kjv")
    )


def _commentary(excerpts: dict[str, Excerpt]) -> str:
    blocks = []
    for c in COMMENTATORS:
        text = excerpts[c].text if excerpts[c].parts else "(No notes on this section.)"
        blocks.append(f'<commentary commentator="{c}" name="{COMMENTATOR_NAMES[c]}">\n{text}\n'
                      "</commentary>")  # fmt: skip
    return "\n\n".join(blocks)


def _ideas_list(ideas: list[Idea]) -> str:
    def line(i: Idea) -> str:
        names = ", ".join(COMMENTATOR_NAMES[s] for s in i.sources)
        agreed = "agreed" if i.agreed else "one commentator"
        scope = f"verses {i.verse_start}-{i.verse_end}"
        central = "CENTRAL MEANING; " if i.central else ""
        return f"- {i.id} [{central}{scope}; {agreed}: {names}] {i.title}: {i.body}"

    key = [line(i) for i in ideas if i.kind == "key"]
    background = [line(i) for i in ideas if i.kind == "background"]
    text = "\n".join(key)
    if background:
        text += (
            "\n\nBackground (facts worth knowing, not meanings; questions must not "
            "target these):\n" + "\n".join(background)
        )
    return text


class GenerateStage(SectionStage):
    name = "generate"

    def _prompts(self, deps: Deps) -> tuple[Any, Any]:
        extract = system_prompt(self.name, deps.settings, prompt="extract")
        questions = system_prompt(
            self.name, deps.settings, prompt="questions", with_question_guide=True
        )
        return extract, questions

    def prompt_version(self, deps: Deps) -> str:
        extract, questions = self._prompts(deps)
        return version_tag({**extract.versions, **questions.versions})

    def model(self, deps: Deps) -> str:
        return deps.settings.stage(self.name).model

    def _excerpts(self, entry: SectionMapEntry, deps: Deps) -> dict[str, Excerpt]:
        return gather_all(
            entry,
            deps.store.book.upper(),
            deps.sources,
            cap_tokens=deps.settings.excerpt_cap_tokens,
        )

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        entry = section_entry(section_id, deps)
        book = deps.store.book.upper()
        return {
            "section": entry.to_doc(),
            "passages": sha256_hex(_passages(deps, book, entry).encode()),
            "excerpts": {c: e.record().sha256 for c, e in self._excerpts(entry, deps).items()},
            "previous": _previous_summary(section_id, deps),
            # A gate stage asked for this section to be regenerated (FR-018).
            "regenerate": draft.regenerate,
        }

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        book = resolve_book(deps.store.book)
        entry = section_entry(section_id, deps)
        excerpts = self._excerpts(entry, deps)
        ctx = CheckContext.for_book(deps.sources, book.code)
        regenerating_for, draft.regenerate = draft.regenerate, None
        extract_prompt, questions_prompt = self._prompts(deps)
        usages: list[Usage] = []
        dropped: list[DroppedItem] = []
        previous = _previous_summary(section_id, deps)

        header = _header(section_id, entry, book.name)
        passages = _passages(deps, book.code, entry)
        extract_user = (
            f"{header}\n"
            f"The previous section, for context only: {previous or '(none: this is the start)'}"
            f"\n\n{passages}\n\n{_commentary(excerpts)}"
        )
        texts = {c: e.text for c, e in excerpts.items()}

        ideas_out: IdeasOut | None = None
        ideas: list[Idea] = []
        for attempt in range(2):
            ideas_out, usage = await deps.runner.parse(
                self.name, extract_prompt.blocks, extract_user, IdeasOut,
                section_id=section_id, call="extract",
            )  # fmt: skip
            usages.append(usage)
            ideas, idea_drops = process_ideas(ideas_out, entry, texts, draft, ctx)
            dropped += idea_drops
            too_long = note_problem(ideas_out)
            if (ideas or ideas_out.no_prompt) and too_long is None:
                break
            if attempt == 1:
                break  # a note still too long fails the check stage, which regenerates once
            if not (ideas or ideas_out.no_prompt):
                extract_user += (
                    "\n\nA previous attempt gave no key idea whose evidence quotes could be found "
                    "in the commentators' notes. Quote their words exactly."
                )
            if too_long is not None:
                dropped += [
                    DroppedItem(item_id=i.id, stage="generate", reason=f"regenerated: {too_long}",
                                item=i.publishable())
                    for i in ideas
                ]  # fmt: skip
                extract_user += (
                    f"\n\nIn a previous attempt {too_long}. Keep every note within its limit."
                )
        assert ideas_out is not None

        no_prompt = ideas_out.no_prompt or not ideas
        no_prompt_reason = ideas_out.no_prompt_reason
        pool = QuestionPool()
        if not ideas and not ideas_out.no_prompt:
            no_prompt_reason = None
            pool.problem = "no key idea passed the evidence check"
        elif not no_prompt:
            # The writer reads the commentators' notes too, for what is worth asking and the angle
            # to ask from (questions/v7). Their conclusions must stay out of the question.
            questions_user = (
                f"{header}\n\n{passages}\n\n"
                f"The commentators' notes (for you, not the reader):\n{_commentary(excerpts)}\n\n"
                f"Key ideas, the central meaning first, then agreed ones:\n"
                f"{_ideas_list(ideas)}\n\n"
                f"Views differ: {ideas_out.views_differ or '(none)'}"
            )
            first_problem: str | None = None
            for attempt in range(2):
                questions_out, usage = await deps.runner.parse(
                    self.name, questions_prompt.blocks, questions_user, QuestionsOut,
                    section_id=section_id, call="questions",
                )  # fmt: skip
                usages.append(usage)
                if first_problem is not None:  # regenerated: keep the first pool on record
                    dropped += [
                        DroppedItem(
                            item_id=q.id, stage="generate",
                            reason=f"regenerated: {first_problem}", item=q.publishable(),
                        )
                        for q in pool.candidates
                    ]  # fmt: skip
                pool = process_questions(questions_out, ideas, entry, draft, ctx)
                dropped += pool.dropped
                if pool.problem is None or attempt == 1:
                    break
                first_problem = pool.problem
                questions_user += (
                    f"\n\nA previous attempt broke a rule: {pool.problem}. Write a new set that "
                    "follows every rule."
                )

        draft.excerpts = {c: e.record() for c, e in excerpts.items()}
        draft.evidence = {i.id: i.evidence for i in ideas}
        draft.no_prompt_reason = no_prompt_reason if no_prompt else None
        # New content replaces the old, and so does everything the gate recorded about it.
        draft.dropped = dropped
        draft.grades, draft.checks = {}, []
        draft.candidates = [q.publishable() for q in pool.candidates]
        draft.central_idea = next((i.id for i in ideas if i.central), None)
        draft.regenerated_for = regenerating_for
        draft.section = {
            "id": section_id,
            "ref": reference(book.name, entry),
            "chapter": entry.chapter,
            "verseStart": entry.verse_start,
            "verseEnd": entry.verse_end,
            "title": entry.title,
            "noPrompt": no_prompt,
            "context": ideas_out.context,
            "viewsDiffer": ideas_out.views_differ,
            "manuscriptNotes": [],
            "keyIdeas": [i.publishable() for i in ideas],
            "questions": [q.publishable() for q in pool.questions],
        }
        draft.failed = pool.problem
        if pool.problem is not None:
            deps.store.write_draft(section_id, draft)  # keep the record and the ID counters
            raise SectionFailed(f"{section_id}: {pool.problem} (after one regeneration)")
        return SectionResult(usages=usages)
