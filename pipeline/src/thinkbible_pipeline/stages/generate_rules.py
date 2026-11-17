"""What code decides after each ``generate`` call (research R10, R11, R13, FR-005-FR-011).

The model proposes; these rules keep only what is grounded and well formed, and record why
anything was dropped:

- **Evidence (R10)**: every cited commentator must be backed by a short quote found in that
  commentator's excerpt. A source without one is removed; an idea left with no sources is dropped.
- **Ideas**: ``agreed`` when two or more commentators make the point; agreed ideas rank first;
  at most 5; verses must lie inside the section.
- **Questions (R11, revised 2026-11-17)**: an ordered list with no levels. The model writes
  candidates in the order a reader should meet them; code keeps up to 3 (never more than the key
  ideas), preferring questions aimed at an idea the earlier ones don't cover, and making sure a
  question on the whole passage is among them when one passed. A section with no usable question
  is regenerated once, then fails (FR-018).
- **IDs (R13)**: every generated item gets the next permanent ID, kept or dropped.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from thinkbible_core.rules import max_questions
from thinkbible_pipeline.drafts.ids import next_id
from thinkbible_pipeline.drafts.models import DroppedItem, Evidence, SectionDraft, SectionMapEntry
from thinkbible_pipeline.gate.checks import CheckContext, idea_problem, question_problem
from thinkbible_pipeline.llm.outputs import IdeaOut, IdeasOut, QuestionOut, QuestionsOut
from thinkbible_pipeline.text import normalize

MAX_IDEAS = 5
MAX_QUOTE_WORDS = 30  # stored evidence is cut to this many words (still a verbatim quote)
MAX_MATCH_WORDS = 80  # a longer quote is checked whole, as long as it is found verbatim
MIN_QUOTE_WORDS = 3


@dataclass
class Idea:
    id: str
    title: str
    body: str
    sources: list[str]
    verse_start: int
    verse_end: int
    evidence: list[Evidence]

    @property
    def agreed(self) -> bool:
        return len(self.sources) >= 2

    def publishable(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "sources": self.sources,
            "agreed": self.agreed,
            "verseStart": self.verse_start,
            "verseEnd": self.verse_end,
            "status": "active",
        }


@dataclass
class Question:
    id: str
    type: str
    verse_start: int
    verse_end: int
    text: str
    targets: list[str]

    def publishable(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "verseStart": self.verse_start,
            "verseEnd": self.verse_end,
            "text": self.text,
            "targets": self.targets,
            "status": "active",
        }


@dataclass
class QuestionPool:
    questions: list[Question] = field(default_factory=list)
    dropped: list[DroppedItem] = field(default_factory=list)
    problem: str | None = None  # why the questions can't ship (regenerate once, then fail)


# --- evidence ---

# Bracketed citations such as "(Mr 1:12)" or "(See on Mt 4:1)": a quote that leaves one out is
# still the commentator's words.
_CITATION = re.compile(r"\([^()]*\d[^()]*\)")


def _match_text(text: str) -> str:
    return normalize(_CITATION.sub(" ", text))


def quote_found(quote: str, excerpt: str) -> bool:
    words = _match_text(quote).split()
    if not MIN_QUOTE_WORDS <= len(words) <= MAX_MATCH_WORDS:
        return False
    return f" {' '.join(words)} " in f" {_match_text(excerpt)} "


def short_quote(quote: str) -> str:
    """The first ``MAX_QUOTE_WORDS`` words of a verified quote: still the commentator's words."""
    words = quote.split()
    return quote.strip() if len(words) <= MAX_QUOTE_WORDS else " ".join(words[:MAX_QUOTE_WORDS])


def _drop(
    item_id: str, reason: str, item: object, stage: Literal["generate", "check"] = "generate"
) -> DroppedItem:
    data = item.model_dump(by_alias=True) if hasattr(item, "model_dump") else dict(vars(item))
    return DroppedItem(item_id=item_id, stage=stage, reason=reason, item=data)


def _in_section(start: int, end: int, section: SectionMapEntry) -> bool:
    return section.verse_start <= start <= end <= section.verse_end


def check_evidence(idea: IdeaOut, excerpts: dict[str, str]) -> tuple[list[str], list[Evidence]]:
    """The sources backed by a quote found in that commentator's excerpt, with those quotes."""
    sources: list[str] = []
    evidence: list[Evidence] = []
    for source in dict.fromkeys(idea.sources):
        quote = next(
            (
                e.quote
                for e in idea.evidence
                if e.commentator == source and quote_found(e.quote, excerpts.get(source, ""))
            ),
            None,
        )
        if quote is not None:
            sources.append(source)
            evidence.append(Evidence(commentator=source, quote=short_quote(quote)))
    return sources, evidence


def process_ideas(
    out: IdeasOut,
    section: SectionMapEntry,
    excerpts: dict[str, str],
    draft: SectionDraft,
    ctx: CheckContext | None = None,
) -> tuple[list[Idea], list[DroppedItem]]:
    """Give every idea an ID, keep the grounded ones that pass the checks (agreed first, at
    most 5)."""
    ctx = ctx or CheckContext()
    kept: list[Idea] = []
    dropped: list[DroppedItem] = []
    for raw in out.key_ideas:
        idea_id = next_id(draft, section.id, "k")
        if not _in_section(raw.verse_start, raw.verse_end, section):
            dropped.append(_drop(idea_id, f"verses {raw.verse_start}-{raw.verse_end} are "
                                 f"outside the section ({section.verse_start}-"
                                 f"{section.verse_end})", raw))  # fmt: skip
            continue
        problem = idea_problem(raw.title, raw.body, ctx)
        if problem:
            dropped.append(_drop(idea_id, problem, raw, "check"))
            continue
        sources, evidence = check_evidence(raw, excerpts)
        if not sources:
            dropped.append(_drop(idea_id, "evidence: no cited commentator's quote was found in "
                                 "their notes", raw))  # fmt: skip
            continue
        kept.append(
            Idea(idea_id, raw.title, raw.body, sources, raw.verse_start, raw.verse_end, evidence)
        )
    kept.sort(key=lambda i: not i.agreed)  # stable: agreed first, otherwise the model's order
    for extra in kept[MAX_IDEAS:]:
        dropped.append(_drop(extra.id, f"more than {MAX_IDEAS} key ideas", extra))
    return kept[:MAX_IDEAS], dropped


# --- questions ---


def process_questions(
    out: QuestionsOut,
    ideas: list[Idea],
    section: SectionMapEntry,
    draft: SectionDraft,
    ctx: CheckContext | None = None,
) -> QuestionPool:
    """Give every candidate an ID, drop those that fail a check, and keep up to 3 in order."""
    ctx = ctx or CheckContext()
    pool = QuestionPool()
    kept_ideas = {i.id for i in ideas}
    idea_texts = [(i.title, i.body) for i in ideas]
    passed: list[tuple[QuestionOut, Question]] = []
    for raw in out.questions:
        qid = next_id(draft, section.id, "q")
        problem = question_problem(raw.text, idea_texts, ctx)
        if problem:
            pool.dropped.append(_drop(qid, problem, raw, "check"))
            continue
        if not _in_section(raw.verse_start, raw.verse_end, section):
            pool.dropped.append(_drop(qid, f"verses {raw.verse_start}-{raw.verse_end} are "
                                      "outside the section", raw))  # fmt: skip
            continue
        targets = [t for t in dict.fromkeys(raw.targets) if t in kept_ideas]
        if not targets:
            pool.dropped.append(_drop(qid, "targets no key idea that was kept", raw))
            continue
        q = Question(qid, raw.type, raw.verse_start, raw.verse_end, raw.text.strip(), targets)
        passed.append((raw, q))

    chosen = choose([q for _, q in passed], max_questions(len(ideas)), lambda q: _whole(q, section))
    pool.questions = [q for _, q in passed if q.id in chosen]
    for raw, q in passed:
        if q.id not in chosen:
            pool.dropped.append(_drop(q.id, f"more than {len(chosen)} questions passed; the "
                                      "earlier ones were kept", raw))  # fmt: skip
    pool.problem = None if pool.questions else "no usable question"
    return pool


def choose(questions: list[Question], cap: int, whole: Callable[[Question], bool]) -> set[str]:
    """The IDs of up to ``cap`` questions, kept in the model's order.

    First, each question that aims at a key idea the ones before it don't; then the rest in order.
    If none of those covers the whole passage, the first whole-passage question takes the last
    place.
    """
    chosen: list[Question] = []
    covered: set[str] = set()
    for q in questions:
        if len(chosen) < cap and set(q.targets) - covered:
            chosen.append(q)
            covered |= set(q.targets)
    for q in questions:
        if len(chosen) < cap and q not in chosen:
            chosen.append(q)
    if cap >= 2 and chosen and not any(whole(q) for q in chosen):
        spare = next((q for q in questions if whole(q) and q not in chosen), None)
        if spare is not None:
            chosen[-1] = spare
    return {q.id for q in chosen}


def _whole(q: Question, section: SectionMapEntry) -> bool:
    return q.verse_start == section.verse_start and q.verse_end == section.verse_end
