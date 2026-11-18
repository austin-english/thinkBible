"""Render ``review.html``: the read-only scorecard and content report for one book (R17).

One self-contained HTML file (no external requests): the headline numbers, failed and
no-question sections, then every section in order with its passage (BSB and KJV), key ideas with
their evidence quotes, the questions in reading order, context, views differ, and what the rules
dropped and why. Verse placeholders read as the app shows them: "(verse 7)".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.drafts.models import SectionDraft, SectionMapEntry
from thinkbible_pipeline.report.scorecard import Scorecard
from thinkbible_pipeline.sections.passage import passage_text
from thinkbible_pipeline.sources.snapshot import SourceLibrary

TEMPLATES = Path(__file__).parent / "templates"
NAMES = {
    "matthew-henry": "Matthew Henry",
    "jamieson-fausset-brown": "Jamieson-Fausset-Brown",
    "adam-clarke": "Adam Clarke",
}
# Drops that are part of choosing a pool, not a sign that something went wrong.
ROUTINE_DROPS = ("regenerated:", "more than ", "not chosen:")
_REF = re.compile(r"(\s*\()?\s*\{\{ref:(\d+):(\d+)(?:-(\d+))?\}\}(\))?")


def readable(text: str, chapter: int) -> str:
    """``{{ref:1:7-8}}`` → ``(verses 7-8)``, as the app renders placeholders.

    A placeholder the text already wraps in parentheses ("({{ref:1:38}})") gets no second pair.
    """

    def sub(m: re.Match[str]) -> str:
        opened, c, a, b, closed = m.group(1), int(m.group(2)), m.group(3), m.group(4), m.group(5)
        if c != chapter:
            label = f"{c}:{a}" + (f"-{b}" if b else "")
        else:
            label = f"verses {a}-{b}" if b else f"verse {a}"
        if opened and closed:
            return f"{opened}{label})"
        return f"{opened or ''} ({label}){closed or ''}"

    return _REF.sub(sub, text)


def _scope(start: int, end: int, entry: SectionMapEntry) -> str:
    if (start, end) == (entry.verse_start, entry.verse_end):
        return "Passage"
    return f"v. {start}" if start == end else f"vv. {start}-{end}"


def _verses(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        number, _, words = line.partition(" ")
        out.append((number, words))
    return out


def _order(commentator: str) -> int:
    return list(NAMES).index(commentator) if commentator in NAMES else len(NAMES)


def section_view(
    entry: SectionMapEntry, draft: SectionDraft | None, book: str, library: SourceLibrary
) -> dict[str, Any]:
    ch = entry.chapter
    view: dict[str, Any] = {
        "entry": entry,
        "ref": f"{resolve_book(book).name} {ch}:{entry.verse_start}-{entry.verse_end}",
        "passage": {t: _verses(passage_text(library, t, book, entry)) for t in ("bsb", "kjv")},
        "generated": draft is not None and "generate" in draft.stages,
        "problem": False,
    }
    if not view["generated"] or draft is None:
        return view
    s = draft.section
    ideas = []
    for i in s.get("keyIdeas", []):
        ideas.append(
            {
                **i,
                "title": readable(i["title"], ch),
                "body": readable(i["body"], ch),
                "scope": _scope(i["verseStart"], i["verseEnd"], entry),
                "names": [NAMES.get(c, c) for c in i["sources"]],
                "grade": draft.grades.get(i["id"]),
                "quotes": [
                    (NAMES.get(q["commentator"], q["commentator"]), q["text"])
                    for q in i.get("quotes", [])
                ],
                "background": i.get("kind") == "background",
            }
        )
    titles = {i["id"]: i["title"] for i in ideas}
    questions = [
        {
            **q,
            "text": readable(q["text"], ch),
            "scope": _scope(q["verseStart"], q["verseEnd"], entry),
            "targets": [titles.get(t, t) for t in q["targets"]],
            "grade": draft.grades.get(q["id"]),
        }
        for q in s.get("questions", [])
    ]
    view.update(
        {
            "ideas": ideas,
            "questions": questions,
            "context": readable(s.get("context") or "", ch),
            "context_grade": draft.grades.get(f"{entry.id}-context"),
            "views_grade": draft.grades.get(f"{entry.id}-views"),
            "views_differ": readable(s["viewsDiffer"], ch) if s.get("viewsDiffer") else None,
            "no_prompt": s.get("noPrompt", False),
            "no_prompt_reason": draft.no_prompt_reason,
            "failed": draft.failed,
            "summary": draft.summary,
            "dropped": [
                {
                    "id": d.item_id,
                    "reason": d.reason,
                    "text": readable(str(d.item.get("title") or d.item.get("text") or ""), ch),
                }
                for d in draft.dropped
            ],
            "excerpts": [
                (NAMES.get(c, c), r.tokens, r.cross_refs, r.trimmed)
                for c, r in sorted(draft.excerpts.items(), key=lambda kv: _order(kv[0]))
            ],
            "cost": sum(r.cost_usd for r in draft.stages.values()),
            # Worth a look: a failure, or an item dropped for being wrong rather than for overflow.
            "problem": bool(draft.failed)
            or any(not d.reason.startswith(ROUTINE_DROPS) for d in draft.dropped),
        }
    )
    return view


def render_review(
    card: Scorecard,
    sections: list[SectionMapEntry],
    drafts: dict[str, SectionDraft],
    library: SourceLibrary,
) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    views = [section_view(e, drafts.get(e.id), card.book, library) for e in sections]
    first = drafts.get(sections[0].id) if sections else None
    intro = first.book_intro if first is not None else None
    return env.get_template("review.html.j2").render(
        card=card,
        sections=views,
        book_name=resolve_book(card.book).name,
        intro=intro,
        names=NAMES,
    )
