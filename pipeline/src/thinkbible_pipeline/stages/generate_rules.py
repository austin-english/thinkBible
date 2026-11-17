"""What code decides after each ``generate`` call (research R10, R11, R13, FR-005-FR-011).

The model proposes; these rules keep only what is grounded and well formed, and record why
anything was dropped:

- **Evidence (R10)**: every cited commentator must be backed by a short quote found in that
  commentator's excerpt. A source without one is removed; an idea left with no sources is dropped.
- **Ideas**: ``agreed`` when two or more commentators make the point; agreed ideas rank first;
  at most 5; verses must lie inside the section.
- **Levels (R11, revised 2026-11-16)**: levels differ by how far a question reaches, not by
  recall versus thinking: every question asks the reader to think. Level 3 when it needs outside
  knowledge, goes beyond the text, or is an application question; Level 1 when it is about one
  detail (at most 2 verses) and needs no outside knowledge; otherwise Level 2 (the passage, or a
  contrast across verses).
- **Pool**: levels are capped by the number of ideas (1 idea: Level 1 only; 2: Levels 1-2; 3+:
  all three); at most 2 questions per level, the second an alternate; every level up to the cap
  needs a question; a section with 2+ levels needs a whole-passage question. When a rule fails
  the questions are regenerated once, then the section fails (FR-018).
- **IDs (R13)**: every generated item gets the next permanent ID, kept or dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from thinkbible_pipeline.drafts.ids import next_id
from thinkbible_pipeline.drafts.models import (
    DroppedItem,
    Evidence,
    QuestionFeatures,
    SectionDraft,
    SectionMapEntry,
)
from thinkbible_pipeline.gate.checks import CheckContext, idea_problem, question_problem
from thinkbible_pipeline.llm.outputs import IdeaOut, IdeasOut, QuestionOut, QuestionsOut
from thinkbible_pipeline.text import normalize

MAX_IDEAS = 5
MAX_PER_LEVEL = 2
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
    level: int
    type: str
    verse_start: int
    verse_end: int
    text: str
    targets: list[str]
    features: QuestionFeatures
    is_alternate: bool = False

    def publishable(self) -> dict[str, object]:
        return {
            "id": self.id,
            "level": self.level,
            "type": self.type,
            "verseStart": self.verse_start,
            "verseEnd": self.verse_end,
            "text": self.text,
            "targets": self.targets,
            "isAlternate": self.is_alternate,
            "status": "active",
        }


@dataclass
class QuestionPool:
    questions: list[Question] = field(default_factory=list)
    dropped: list[DroppedItem] = field(default_factory=list)
    problem: str | None = None  # why the pool breaks a rule (regenerate once, then fail)


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


def level_for(q: QuestionOut) -> int:
    span = q.verse_end - q.verse_start + 1
    if (
        q.outside_knowledge == "required"
        or q.answer_directness == "beyond"
        or q.type == "application"
    ):
        return 3
    if span <= 2 and q.outside_knowledge == "none":
        return 1
    return 2


def max_level(ideas: list[Idea]) -> int:
    return min(3, len(ideas))


def process_questions(
    out: QuestionsOut,
    ideas: list[Idea],
    section: SectionMapEntry,
    draft: SectionDraft,
    ctx: CheckContext | None = None,
) -> QuestionPool:
    """Give every question an ID and a level, then choose the pool.

    Within each level, a question on the whole passage is preferred (a pool with 2+ levels needs
    one), then the model's order. The alternate is preferably aimed at a different key idea than
    the primary, so it can serve a reader who missed that idea.
    """
    ctx = ctx or CheckContext()
    pool = QuestionPool()
    agreement = {i.id: len(i.sources) for i in ideas}
    idea_texts = [(i.title, i.body) for i in ideas]
    cap = max_level(ideas)
    by_level: dict[int, list[tuple[QuestionOut, Question]]] = {}
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
        targets = [t for t in dict.fromkeys(raw.targets) if t in agreement]
        if not targets:
            pool.dropped.append(_drop(qid, "targets no key idea that was kept", raw))
            continue
        level = level_for(raw)
        if level > cap:
            pool.dropped.append(_drop(qid, f"Level {level} needs at least {level} key ideas "
                                      f"(this section has {len(ideas)})", raw))  # fmt: skip
            continue
        by_level.setdefault(level, []).append(
            (
                raw,
                Question(
                    id=qid,
                    level=level,
                    type=raw.type,
                    verse_start=raw.verse_start,
                    verse_end=raw.verse_end,
                    text=raw.text.strip(),
                    targets=targets,
                    features=QuestionFeatures(
                        answer_directness=raw.answer_directness,
                        outside_knowledge=raw.outside_knowledge,
                        verse_span=raw.verse_end - raw.verse_start + 1,
                        agreement=max(agreement[t] for t in targets),
                    ),
                ),
            )
        )
    for level in sorted(by_level):
        candidates = sorted(by_level[level], key=lambda c: not _whole(c[1], section))  # stable
        primary = candidates[0][1]
        rest = candidates[1:]
        alternate = next((c for c in rest if set(c[1].targets) != set(primary.targets)), None)
        if alternate is None and rest:
            alternate = rest[0]
        pool.questions.append(primary)
        if alternate is not None:
            alternate[1].is_alternate = True
            pool.questions.append(alternate[1])
        for raw, q in rest:
            if alternate is None or q is not alternate[1]:
                pool.dropped.append(_drop(q.id, f"Level {level} already has {MAX_PER_LEVEL} "
                                          "questions", raw))  # fmt: skip
    pool.questions.sort(key=lambda q: (q.level, q.is_alternate))
    pool.problem = pool_problem(pool.questions, cap, section)
    return pool


def _whole(q: Question, section: SectionMapEntry) -> bool:
    return q.verse_start == section.verse_start and q.verse_end == section.verse_end


def pool_problem(questions: list[Question], cap: int, section: SectionMapEntry) -> str | None:
    """Why this pool can't ship, or None (R11)."""
    if not questions:
        return "no usable question"
    missing = [lvl for lvl in range(1, cap + 1) if not any(q.level == lvl for q in questions)]
    if missing:
        return "no Level " + " or ".join(str(m) for m in missing) + " question"
    if cap >= 2 and not any(_whole(q, section) for q in questions):
        return "no question on the whole passage"
    return None
