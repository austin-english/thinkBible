"""The ``align`` stage (T077, R3, R12): KJV wording variants and manuscript notes.

Runs after ``generate`` and before ``check``, so the checks and the grader see the section as it
will be published.

1. **KJV variants.** For every candidate question, code finds what a KJV reader wouldn't find in
   their verses: a quoted phrase the KJV words differently, or a name it spells differently
   (``align_rules.bsb_only_words``). Only those questions go to the model (Haiku,
   ``prompts/align``), which writes the question with the KJV's words, or returns it unchanged
   when it already reads naturally. A variant is kept as ``textByTranslation.kjv`` if it differs,
   ends with "?" and is 10 to 200 characters; otherwise it is logged as refused.
2. **Manuscript notes**, written in code (``align_rules.manuscript_candidates``): verses one
   translation has and the other doesn't, and passages early manuscripts end before.

Everything it adds or refuses is listed in the draft's ``alignment`` for the report. The review
stage copies the kept questions from the candidates, so their variants come with them.
"""

from __future__ import annotations

from typing import Any

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.drafts.models import SectionDraft
from thinkbible_pipeline.llm.outputs import AlignVariantOut
from thinkbible_pipeline.llm.prompts import system_prompt, version_tag
from thinkbible_pipeline.llm.runner import Usage
from thinkbible_pipeline.stages.align_rules import (
    book_text,
    bsb_only_words,
    manuscript_candidates,
    verse_text,
)
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage
from thinkbible_pipeline.stages.summaries import section_entry

# Bump when the detection or the notes' wording changes, so every section is aligned again.
ALIGN_RULES = "2026-11-19: quoted phrases and names; notes for whole verses and endings"
QUESTION_MIN, QUESTION_MAX = 10, 200  # section.schema.json questionText


def variant_problem(variant: str, original: str) -> str | None:
    """Why a KJV variant can't be published, or None."""
    if variant.strip() == original.strip():
        return "unchanged"
    if not variant.endswith("?"):
        return "doesn't end with '?'"
    if not QUESTION_MIN <= len(variant) <= QUESTION_MAX:
        return f"{len(variant)} characters (10 to 200)"
    if '"' in variant:
        return "uses double quotation marks"
    return None


def _stamp(draft: SectionDraft, stage: str) -> str | None:
    rec = draft.stages.get(stage)
    return f"{rec.status}:{rec.input_hash}@{rec.completed_at}" if rec else None


class AlignStage(SectionStage):
    name = "align"

    def prompt_version(self, deps: Deps) -> str:
        return version_tag(system_prompt(self.name, deps.settings).versions)

    def model(self, deps: Deps) -> str:
        return deps.settings.stage(self.name).model

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        return {"generate": _stamp(draft, "generate"), "rules": ALIGN_RULES}

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        rec = draft.stages.get("generate")
        if rec is None or rec.status != "done":
            return SectionResult()
        entry = section_entry(section_id, deps)
        book = resolve_book(deps.store.book)
        bsb = deps.sources.translation("bsb", book.code)
        kjv = deps.sources.translation("kjv", book.code)
        bsb_book, kjv_book = book_text(bsb), book_text(kjv)
        prompt = system_prompt(self.name, deps.settings)
        log: list[dict[str, Any]] = []
        usages: list[Usage] = []
        candidates = draft.candidates or draft.section.get("questions", [])
        for q in candidates:
            q.pop("textByTranslation", None)
            bsb_verses = verse_text(bsb, entry.chapter, q["verseStart"], q["verseEnd"])
            kjv_verses = verse_text(kjv, entry.chapter, q["verseStart"], q["verseEnd"])
            words = bsb_only_words(q["text"], bsb_verses, kjv_verses, bsb_book, kjv_book)
            if not words:
                continue
            user = (
                f"Question: {q['text']}\n"
                f"Words a KJV reader won't find in their verses: {', '.join(words)}\n\n"
                f'<passage translation="BSB">\n{bsb_verses}\n</passage>\n\n'
                f'<passage translation="KJV">\n{kjv_verses}\n</passage>'
            )
            out, usage = await deps.runner.parse(
                self.name, prompt.blocks, user, AlignVariantOut,
                section_id=section_id, call=q["id"],
            )  # fmt: skip
            usages.append(usage)
            variant = " ".join(out.text.split())
            problem = variant_problem(variant, q["text"])
            if problem is None:
                q["textByTranslation"] = {"kjv": variant}
                log.append({"kind": "variant", "itemId": q["id"], "words": words,
                            "text": q["text"], "kjv": variant})  # fmt: skip
            elif problem != "unchanged":
                log.append({"kind": "refused", "itemId": q["id"], "words": words,
                            "text": q["text"], "kjv": variant, "reason": problem})  # fmt: skip
        variants = {q["id"]: q["textByTranslation"] for q in candidates if "textByTranslation" in q}
        questions = []
        for q in draft.section.get("questions", []):
            q = {k: v for k, v in q.items() if k != "textByTranslation"}
            if q["id"] in variants:
                q["textByTranslation"] = variants[q["id"]]
            questions.append(q)
        notes = manuscript_candidates(
            bsb, kjv, book.name, entry.chapter, entry.verse_start, entry.verse_end
        )
        draft.section = {
            **draft.section,
            "questions": questions,
            "manuscriptNotes": [
                {"chapter": n.chapter, "verseStart": n.verse_start, "verseEnd": n.verse_end,
                 "text": n.text}
                for n in notes
            ],
        }  # fmt: skip
        log += [
            {"kind": "note", "verses": f"{n.chapter}:{n.verse_start}-{n.verse_end}", "text": n.text}
            for n in notes
        ]
        draft.alignment = log
        return SectionResult(usages=usages)
