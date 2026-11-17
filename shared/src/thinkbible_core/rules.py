"""Cross-field rules that JSON Schema cannot express (data-model.md, "Cross-field rules" 1-9).

Single-object rules (``agreed`` matches sources, retiredIn present when retired, ranges not
backwards) are enforced by the models themselves. This module checks rules that span a section or
a whole pack. Used by the pipeline's ``check`` stage and by ``publish``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import pairwise

from thinkbible_core.models import KeyIdea, Question, Section, StudyPack, VerseText
from thinkbible_core.refs import malformed, unresolved

MAX_ACTIVE_QUESTIONS = 3


@dataclass(frozen=True)
class Violation:
    rule: int
    item_id: str
    message: str

    def __str__(self) -> str:
        return f"rule {self.rule} [{self.item_id}]: {self.message}"


def max_questions(active_idea_count: int) -> int:
    """How many active questions a section may have: one per active key idea, at most 3 (FR-009).

    Questions are an ordered list with no levels (revised 2026-11-17): the reader meets the first
    on the first read, and each next one a week after answering the one before.
    """
    return min(active_idea_count, MAX_ACTIVE_QUESTIONS)


def cross_field_violations(
    pack: StudyPack, verses: Mapping[str, VerseText] | None = None
) -> list[Violation]:
    """All cross-field violations in ``pack``.

    ``verses`` (translation id -> VerseText) enables the rules that need verse text: full coverage
    of every verse present in either translation (rule 1) and placeholder resolution (rule 8).
    """
    verse_sets = {tr: vt.verse_set() for tr, vt in (verses or {}).items()}
    out: list[Violation] = []
    out += _coverage(pack.sections, verse_sets)
    seen_ids: set[str] = set()
    for section in pack.sections:
        out += _section_rules(section, seen_ids, verse_sets)
    return out


def section_violations(
    section: Section, verse_sets: Mapping[str, Iterable[tuple[int, int]]] | None = None
) -> list[Violation]:
    """Rules 2-9 for a single section (used on drafts, before a pack exists)."""
    sets = {tr: set(vs) for tr, vs in (verse_sets or {}).items()}
    return _section_rules(section, set(), sets)


# --- rule 1: coverage -----------------------------------------------------------------------------


def _coverage(
    sections: list[Section], verse_sets: Mapping[str, set[tuple[int, int]]]
) -> list[Violation]:
    out: list[Violation] = []
    by_chapter: dict[int, list[Section]] = defaultdict(list)
    for s in sections:
        by_chapter[s.chapter].append(s)

    for chapter, secs in sorted(by_chapter.items()):
        secs.sort(key=lambda s: s.verse_start)
        for prev, cur in pairwise(secs):
            if cur.verse_start <= prev.verse_end:
                out.append(Violation(1, cur.id, f"overlaps {prev.id}"))
            elif cur.verse_start != prev.verse_end + 1:
                out.append(
                    Violation(
                        1,
                        cur.id,
                        f"gap after {prev.id} (verses "
                        f"{prev.verse_end + 1}-{cur.verse_start - 1} not in any section)",
                    )
                )
        if verse_sets:
            present = {v for vs in verse_sets.values() for (c, v) in vs if c == chapter}
            covered = {v for s in secs for v in range(s.verse_start, s.verse_end + 1)}
            missing = sorted(present - covered)
            if missing:
                out.append(
                    Violation(1, f"chapter {chapter}", f"verses not in any section: {missing}")
                )
            beyond = sorted(covered - present)
            if beyond and present:
                out.append(
                    Violation(
                        1,
                        f"chapter {chapter}",
                        f"sections cover verses no translation has: {beyond}",
                    )
                )
    return out


# --- rules 2-9: per section -----------------------------------------------------------------------


def _section_rules(
    s: Section, seen_ids: set[str], verse_sets: Mapping[str, set[tuple[int, int]]]
) -> list[Violation]:
    out: list[Violation] = []
    ideas = {k.id: k for k in s.key_ideas}
    active_ideas = {k.id for k in s.key_ideas if k.status == "active"}
    # Only ideas a reader can see in the passage are targeted and counted (kind "key").
    active_key = {k.id for k in s.key_ideas if k.status == "active" and k.kind == "key"}
    background = {k.id for k in s.key_ideas if k.kind == "background"}
    active_qs = [q for q in s.questions if q.status == "active"]
    items: list[KeyIdea | Question] = [*s.key_ideas, *s.questions]

    # 2: item ranges inside the section
    for item in items:
        if item.verse_start < s.verse_start or item.verse_end > s.verse_end:
            out.append(
                Violation(
                    2,
                    item.id,
                    f"range {item.verse_start}-{item.verse_end} "
                    f"is outside section {s.verse_start}-{s.verse_end}",
                )
            )

    # 3: IDs prefixed by the section ID and unique
    for item in items:
        if not item.id.startswith(f"{s.id}-"):
            out.append(Violation(3, item.id, f"id does not start with section id {s.id}"))
        if item.id in seen_ids:
            out.append(Violation(3, item.id, "duplicate id"))
        seen_ids.add(item.id)
    if s.id in seen_ids:
        out.append(Violation(3, s.id, "duplicate section id"))
    seen_ids.add(s.id)

    # 4: agreed consistent with sources (also enforced by the model)
    for k in s.key_ideas:
        if k.agreed != (len(k.sources) >= 2):
            out.append(Violation(4, k.id, "agreed must be true exactly when 2+ sources"))

    # 5 + 9: targets are active ideas in the same section
    for q in active_qs:
        unknown = [t for t in q.targets if t not in ideas]
        if unknown:
            out.append(Violation(5, q.id, f"targets ideas not in this section: {unknown}"))
        known = [t for t in q.targets if t in ideas]
        retired = [t for t in known if t not in active_ideas]
        if known and len(retired) == len(known):
            out.append(Violation(9, q.id, "active question targets only retired ideas; retire it"))
        elif retired:
            out.append(Violation(5, q.id, f"targets retired ideas: {retired}"))
        aimed_at_background = [t for t in q.targets if t in background]
        if aimed_at_background:
            message = f"targets background ideas (not in the passage): {aimed_at_background}"
            out.append(Violation(5, q.id, message))

    # 6 + 7: question list shape
    if s.no_prompt:
        if active_qs:
            out.append(Violation(7, s.id, "noPrompt section has active questions"))
    else:
        out += _question_rules(s.id, len(active_key), active_qs)

    # 8: placeholders well-formed and resolvable
    for item_id, text in _texts(s):
        for frag in malformed(text):
            out.append(Violation(8, item_id, f"malformed placeholder {frag!r}"))
        for tr, ref in unresolved(text, verse_sets):
            out.append(Violation(8, item_id, f"{ref} does not resolve in {tr}"))
    return out


def _question_rules(section_id: str, n_ideas: int, qs: list[Question]) -> list[Violation]:
    if n_ideas == 0:
        return [Violation(7, section_id, "prompted section has no active key idea of kind 'key'")]
    if not qs:
        return [Violation(7, section_id, "prompted section has no active question")]
    cap = max_questions(n_ideas)
    if len(qs) > cap:
        return [
            Violation(
                6,
                section_id,
                f"{len(qs)} active questions (at most {cap} with {n_ideas} key ideas)",
            )
        ]
    return []


def _texts(s: Section) -> list[tuple[str, str]]:
    texts = [(s.id, s.context)]
    if s.views_differ:
        texts.append((s.id, s.views_differ))
    texts += [(s.id, n.text) for n in s.manuscript_notes]
    for k in s.key_ideas:
        texts += [(k.id, k.title), (k.id, k.body)]
    for q in s.questions:
        texts.append((q.id, q.text))
        texts += [(q.id, t) for t in (q.text_by_translation or {}).values()]
    return texts
