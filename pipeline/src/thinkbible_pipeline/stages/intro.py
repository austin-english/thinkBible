"""The ``intro`` stage (2026-11-18): the book introduction, the first post of the book in the feed.

It runs once per book, on the book's first section (whose draft keeps it, so publishing can lift
it into the pack's ``introduction``). Each commentator's preface to the book comes from their first
note (``commentary/preface.py``); sections no longer see the prefaces, so their context notes stay
about the passage.

1. ``write`` (the generate model): 80 to 120 words, sources and an evidence quote from each.
2. The evidence check, as for key ideas: a source without a quote found in its preface is dropped.
3. ``grade`` (the review model, ``prompts/intro-review``): 1 to 5. At or below
   ``review_flag_threshold`` the introduction is written once more with the reason given; if it
   fails again, ``problem`` says why and the scorecard lists it as a blocker.

A book whose commentators give no preface gets no introduction, which is not a problem.
"""

from __future__ import annotations

from typing import Any

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.commentary.gather import book_prefaces
from thinkbible_pipeline.drafts.models import BookIntro, Grade, SectionDraft
from thinkbible_pipeline.gate.checks import _COMMENTATOR
from thinkbible_pipeline.jsonio import sha256_hex
from thinkbible_pipeline.llm.outputs import IntroOut, ReviewOut
from thinkbible_pipeline.llm.prompts import system_prompt, version_tag
from thinkbible_pipeline.llm.runner import Usage
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage
from thinkbible_pipeline.stages.generate import COMMENTATOR_NAMES
from thinkbible_pipeline.stages.generate_rules import check_evidence, display_quote

MAX_CHARS = 900  # section.schema.json bookIntroduction.text
MIN_WORDS, MAX_WORDS = 40, 160  # the prompt asks for 80-120; anything far outside is broken


def is_first_section(section_id: str) -> bool:
    """Every book's first section starts at chapter 1, verse 1 (``mrk-1-1``)."""
    return section_id.endswith("-1-1")


def intro_problem(text: str, sources: list[str]) -> str | None:
    """Why the introduction can't ship as written, or None."""
    words = len(text.split())
    if not sources:
        return "evidence: no source's quote was found in that commentator's preface"
    if len(text) > MAX_CHARS or not MIN_WORDS <= words <= MAX_WORDS:
        return f"length {words} words, {len(text)} characters (80 to 120 words)"
    named = _COMMENTATOR.search(text)
    if named:
        return f"names a commentator ({named.group(1)}); the app shows the sources"
    return None


class IntroStage(SectionStage):
    name = "intro"

    def _prompts(self, deps: Deps) -> tuple[Any, Any]:
        return (
            system_prompt(self.name, deps.settings),
            system_prompt(self.name, deps.settings, prompt="intro-review"),
        )

    def prompt_version(self, deps: Deps) -> str:
        write, grade = self._prompts(deps)
        return version_tag({**write.versions, **grade.versions})

    def model(self, deps: Deps) -> str:
        return deps.settings.stage(self.name).model

    def applies_to(self, section_id: str, deps: Deps) -> bool:
        return is_first_section(section_id)

    def _prefaces(self, deps: Deps) -> dict[str, str]:
        book = resolve_book(deps.store.book)
        return book_prefaces(book.code, deps.sources, cap_tokens=deps.settings.excerpt_cap_tokens)

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        return {
            "prefaces": {c: sha256_hex(t.encode()) for c, t in self._prefaces(deps).items()},
            "grader": deps.settings.stage("review").model,
        }

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        prefaces = self._prefaces(deps)
        if not prefaces:
            draft.book_intro = None  # no commentator prefaces this book
            return SectionResult()
        book = resolve_book(deps.store.book)
        write, grade_prompt = self._prompts(deps)
        notes = "\n\n".join(
            f'<preface commentator="{c}" name="{COMMENTATOR_NAMES[c]}">\n{text}\n</preface>'
            for c, text in prefaces.items()
        )
        user = f"Book: {book.name}\n\n{notes}"
        usages: list[Usage] = []
        feedback = ""
        intro = BookIntro()
        for _attempt in range(2):
            out, usage = await deps.runner.parse(
                self.name, write.blocks, user + feedback, IntroOut,
                section_id=section_id, call="write",
            )  # fmt: skip
            usages.append(usage)
            sources, evidence = check_evidence(out, prefaces)
            text = out.text.strip()
            intro = BookIntro(evidence=evidence, problem=intro_problem(text, sources))
            if intro.problem is None:
                quotes = "\n".join(
                    f"- {COMMENTATOR_NAMES[e.commentator]}: '{e.quote}'" for e in evidence
                )
                to_grade = f"Introduction (item id: intro):\n{text}\n\nIn their words:\n{quotes}"
                graded, usage = await deps.runner.parse(
                    "review", grade_prompt.blocks, f"{user}\n\n{to_grade}",
                    ReviewOut, section_id=section_id, call="intro",
                )  # fmt: skip
                usages.append(usage)
                item = next(iter(graded.items), None)
                if item is not None:
                    score = max(1, min(5, item.score))
                    rules = (
                        f" (breaks: {', '.join(item.failed_rules)})" if item.failed_rules else ""
                    )
                    intro.grade = Grade(score=score, notes=item.reason.strip() + rules)
                    if score <= deps.settings.review_flag_threshold:
                        intro.problem = f"graded {score}: {item.reason.strip()}"
            if intro.problem is None:
                intro.introduction = {
                    "text": text,
                    "sources": sources,
                    "quotes": [
                        {"commentator": e.commentator, "text": display_quote(e.quote)}
                        for e in evidence
                    ],
                }
                break
            feedback = (
                f"\n\nA previous attempt was rejected: {intro.problem}. "
                "Write it again, fixing that."
            )
        draft.book_intro = intro
        return SectionResult(usages=usages)
