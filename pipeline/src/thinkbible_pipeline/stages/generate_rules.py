"""What code decides after each ``generate`` call (research R10, R11, R13, FR-005-FR-011).

The model proposes; these rules keep only what is grounded and well formed, and record why
anything was dropped:

- **Evidence (R10)**: every cited commentator must be backed by a short quote found in that
  commentator's excerpt. A source without one is removed; an idea left with no sources is dropped.
- **Ideas**: ``agreed`` when two or more commentators make the point; agreed ideas rank first;
  at most 5; verses must lie inside the section.
- **Questions (R11, revised 2026-11-17)**: an ordered list with no levels. The model writes
  up to 8 candidates in the order a reader should meet them. Every one that passes the checks is
  kept as a candidate; the grader scores them all and ``review`` keeps the best 3 (never more than
  the key ideas), one per idea first, in the writer's order (``gate.outcomes.pick_best``). Until
  then the section holds the first ones, preferring questions aimed at an idea not yet covered.
  A section with no usable question is regenerated once, then fails (FR-018). (A rule that
  swapped in a whole-passage question was removed on 2026-11-17: in Mark 1:16-20 it replaced the
  'fishers of men' question with a weaker repeat. The prompt asks for a whole-passage question
  first.)
- **IDs (R13)**: every generated item gets the next permanent ID, kept or dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from thinkbible_core.rules import max_questions
from thinkbible_pipeline.drafts.ids import next_id
from thinkbible_pipeline.drafts.models import DroppedItem, Evidence, SectionDraft, SectionMapEntry
from thinkbible_pipeline.gate.checks import CheckContext, idea_problem, question_problem
from thinkbible_pipeline.llm.outputs import IdeaOut, IdeasOut, QuestionOut, QuestionsOut
from thinkbible_pipeline.text import normalize

MAX_IDEAS = 5  # of kind "key"
MAX_BACKGROUND = 2  # of kind "background"
CONTEXT_MAX, VIEWS_DIFFER_MAX = 280, 400  # section.schema.json
MAX_QUOTE_WORDS = 30  # stored evidence is cut to this many words (still a verbatim quote)
MAX_MATCH_WORDS = 80  # a longer quote is checked whole, as long as it is found verbatim
MIN_QUOTE_WORDS = 3


@dataclass
class Idea:
    id: str
    kind: str  # "key" (a deeper meaning) or "background" (a fact worth knowing)
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
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "sources": self.sources,
            # "In their words": the verified evidence quotes, one per source, in source order.
            "quotes": [
                {"commentator": e.commentator, "text": display_quote(e.quote)}
                for e in self.evidence
            ],
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
    questions: list[Question] = field(default_factory=list)  # until review chooses: the first 3
    candidates: list[Question] = field(default_factory=list)  # every question that passed
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


_STRONG_BREAK = re.compile(r"[.;:!?]$")
_COMMA = re.compile(r",$")
MIN_CUT_WORDS = 12  # a cut at a full stop or semicolon must keep at least this many words


def short_quote(quote: str) -> str:
    """A verified quote cut to at most ``MAX_QUOTE_WORDS`` words: still the commentator's words.

    A long quote is cut at a clause break within the limit, so readers don't see words that stop
    mid-phrase ("…or the schools of"): the last full stop, semicolon or colon that keeps at least
    ``MIN_CUT_WORDS`` words, else the last comma, else the limit itself.
    """
    words = quote.split()
    if len(words) <= MAX_QUOTE_WORDS:
        return quote.strip()
    head = words[:MAX_QUOTE_WORDS]
    for pattern, least in ((_STRONG_BREAK, MIN_CUT_WORDS), (_COMMA, MIN_QUOTE_WORDS)):
        for n in range(len(head), least - 1, -1):
            if pattern.search(head[n - 1]):
                return " ".join(head[:n])
    return " ".join(head)


def display_quote(quote: str) -> str:
    """How a verified quote reads under "In their words".

    The words are the commentator's own; only the edges and dashes change: "…" where the quote
    starts or stops mid-sentence (a trailing comma, semicolon or colon gives way to it), and the
    old double hyphen as a dash (JFB's "pleased--The verb").
    """
    text = quote.strip().replace(" -- ", " — ").replace("--", "—")
    if text and text[0].islower():
        text = "…" + text
    if not text.endswith((".", "!", "?", "…", "'", "\u2019", '"', "\u201d")):
        text = text.rstrip(",;: ") + "…"
    return text


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
            Idea(
                idea_id,
                raw.kind,
                raw.title,
                raw.body,
                sources,
                raw.verse_start,
                raw.verse_end,
                evidence,
            )
        )
    kept.sort(key=lambda i: not i.agreed)  # stable: agreed first, otherwise the model's order
    key = [i for i in kept if i.kind == "key"]
    background = [i for i in kept if i.kind == "background"]
    for extra in key[MAX_IDEAS:]:
        dropped.append(_drop(extra.id, f"more than {MAX_IDEAS} key ideas", extra))
    for extra in background[MAX_BACKGROUND:]:
        dropped.append(_drop(extra.id, f"more than {MAX_BACKGROUND} background ideas", extra))
    return key[:MAX_IDEAS] + background[:MAX_BACKGROUND], dropped


def note_problem(out: IdeasOut) -> str | None:
    """Why the context or views-differ note is too long for the pack, or None.

    Models count characters poorly, so ``generate`` asks once more instead of letting the
    ``check`` stage fail the whole section later (Mark 1:21-28: a 287-character context note).
    """
    if len(out.context) > CONTEXT_MAX:
        return f"the context note was {len(out.context)} characters (at most {CONTEXT_MAX})"
    if out.views_differ and len(out.views_differ) > VIEWS_DIFFER_MAX:
        return (
            f"the views-differ note was {len(out.views_differ)} characters "
            f"(at most {VIEWS_DIFFER_MAX})"
        )
    return None


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
    kept_ideas = {i.id for i in ideas if i.kind == "key"}  # background ideas are never targeted
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

    pool.candidates = [q for _, q in passed]
    # Until the grader picks the best (``review``), the section holds the first ones.
    chosen = choose(pool.candidates, max_questions(len(kept_ideas)))
    pool.questions = [q for q in pool.candidates if q.id in chosen]
    pool.problem = None if pool.questions else "no usable question"
    return pool


def choose(questions: list[Question], cap: int) -> set[str]:
    """The IDs of up to ``cap`` questions, kept in the model's order.

    First, each question that aims at a key idea the ones before it don't; then the rest in order.
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
    return {q.id for q in chosen}
