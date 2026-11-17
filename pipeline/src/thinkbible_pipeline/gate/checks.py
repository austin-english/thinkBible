"""The quality gate's rule checks (FR-016, spec Story 2 scenario 1): code only, no model calls.

Item checks run inside ``generate`` before the questions are chosen, so a failing item is
replaced by the next candidate or a regeneration like any other drop; they are recorded with
``stage: "check"``.
Section checks (the pack schema and the shared cross-field rules) run in the ``check`` stage on the
finished section, as the gate's last word before grading.

Each check returns a reason, or None when the item passes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from thinkbible_core.models import Section
from thinkbible_core.refs import malformed, unresolved
from thinkbible_core.rules import section_violations
from thinkbible_core.schema import validate
from thinkbible_pipeline.sources.models import VerseItem
from thinkbible_pipeline.sources.snapshot import SourceLibrary
from thinkbible_pipeline.text import normalize

# Bump when a check is added or changed: the check stage then re-checks every section.
CHECKS_VERSION = "checks-v2"

TITLE_MAX, BODY_MAX = 60, 240
QUESTION_MIN, QUESTION_MAX = 10, 200  # raised from 160 on 2026-11-17

_YES_NO_START = re.compile(
    r"^(is|are|do|does|did|can|could|will|would|was|were|has|have|had|should|shall|may|might|must)\b",
    re.I,
)
_OPEN_WORDS = re.compile(r"\b(what|why|how|which|who|whom|whose|where|when|in what way)\b", re.I)
# The commentators' names: idea text and questions never name them (the app shows sources).
_COMMENTATOR = re.compile(r"\b(Henry|Jamieson|Fausset|Clarke|JFB)\b")


@dataclass(frozen=True)
class CheckContext:
    """What the checks need beyond the item: the verses each translation has."""

    verse_sets: Mapping[str, set[tuple[int, int]]] = field(default_factory=dict)

    @classmethod
    def for_book(cls, library: SourceLibrary, book: str) -> CheckContext:
        sets: dict[str, set[tuple[int, int]]] = {}
        for tr in ("bsb", "kjv"):
            sets[tr] = {
                (c.number, i.number)
                for c in library.translation(tr, book).chapters
                for i in c.items
                if isinstance(i, VerseItem)
            }
        return cls(verse_sets=sets)


def _placeholders(text: str, ctx: CheckContext) -> str | None:
    bad = malformed(text)
    if bad:
        return f"malformed verse placeholder {bad[0]!r}"
    missing = unresolved(text, ctx.verse_sets)
    if missing:
        tr, ref = missing[0]
        return f"verse placeholder {ref} doesn't resolve in {tr.upper()}"
    return None


def idea_problem(title: str, body: str, ctx: CheckContext) -> str | None:
    if not title.strip() or len(title) > TITLE_MAX:
        return f"title length {len(title)} (1 to {TITLE_MAX} characters)"
    if not body.strip() or len(body) > BODY_MAX:
        return f"body length {len(body)} (1 to {BODY_MAX} characters)"
    if not body.strip().endswith((".", "!", "?", ")")):
        return "incomplete text: the body stops mid-sentence"
    named = _COMMENTATOR.search(f"{title} {body}")
    if named:
        return f"names a commentator ({named.group(1)}); the app shows the sources"
    return _placeholders(title, ctx) or _placeholders(body, ctx)


def _question_sentence(text: str) -> str:
    """The sentence that asks: the last one ending in '?' (after any framing sentence)."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return next((s for s in reversed(sentences) if s.endswith("?")), sentences[-1])


def is_yes_no(text: str) -> bool:
    ask = _question_sentence(text)
    return bool(_YES_NO_START.match(ask)) and not _OPEN_WORDS.search(ask)


def repeats_idea(text: str, ideas: list[tuple[str, str]]) -> str | None:
    """The title of an idea whose title the question repeats word for word, or None."""
    q = f" {normalize(text)} "
    for title, _body in ideas:
        t = normalize(title)
        if len(t.split()) >= 3 and f" {t} " in q:
            return title
    # No check against the idea's body: a plain question describes the same scene the body does
    # (Mark 1:21-28 lost its best question to an 8-word overlap). The grader's not-leading line
    # judges whether a question gives the point away.
    return None


def question_problem(text: str, ideas: list[tuple[str, str]], ctx: CheckContext) -> str | None:
    """``ideas``: (title, body) of the section's key ideas."""
    stripped = text.strip()
    if not stripped.endswith("?"):
        return "incomplete question: it must be a whole question ending with '?'"
    if not QUESTION_MIN <= len(stripped) <= QUESTION_MAX:
        return f"question length {len(stripped)} ({QUESTION_MIN} to {QUESTION_MAX} characters)"
    if is_yes_no(stripped):
        return "yes/no question: it must be open-ended"
    named = _COMMENTATOR.search(stripped)
    if named:
        return f"names a commentator ({named.group(1)}); readers haven't seen the commentary yet"
    repeated = repeats_idea(stripped, ideas)
    if repeated:
        return f"gives away a key idea word for word ({repeated!r})"
    return _placeholders(stripped, ctx)


def section_problems(section: dict[str, Any], ctx: CheckContext) -> list[str]:
    """The finished section against the pack schema and the shared cross-field rules.

    Drafts get ``addedIn`` only when published, so a placeholder version stands in for it here.
    """
    doc = {
        **section,
        "keyIdeas": [{"addedIn": "0.0.0", **k} for k in section.get("keyIdeas", [])],
        "questions": [{"addedIn": "0.0.0", **q} for q in section.get("questions", [])],
    }
    problems = [f"schema: {e}" for e in validate(doc, "section")]
    if problems:
        return problems
    model = Section.model_validate(doc)
    return [
        f"rule {v.rule} [{v.item_id}]: {v.message}"
        for v in section_violations(model, ctx.verse_sets)
    ]
