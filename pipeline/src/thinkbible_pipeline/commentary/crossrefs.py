"""Find where a commentator points to their own note on another passage (research R4).

JFB and Clarke often write their note once, on the parallel Gospel, and point to it: "See on
Mt 12:9-21", "See the note on Mat 3:4", "( = Mt 3:1-12; Lu 3:1-18)". Henry writes "which we had
before, Matt. viii. 2-4". Gathering follows these pointers one hop, so a section gets the note the
commentator meant for it.

The note's tagged references (``refs``, from the module's markup) are exact, but they don't say
which ones are pointers. So the pointer phrases are found in the text, the passage after each is
read loosely (abbreviations such as ``Mr``, ``Lu``, ``Joh``, Henry's Roman-numeral chapters), and a
tagged reference to the same book and chapter, when there is one, supplies the exact range.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from thinkbible_core.ids import BOOKS
from thinkbible_pipeline.sources.refs import BOOK_BY_NAME, Ref, parse_compact
from thinkbible_pipeline.sources.versification import KJV_VERSES

PointerKind = Literal["see", "parallel"]

# Book names as commentators write them: the OSIS aliases plus older and fuller forms.
_DISPLAY_NAMES: dict[str, str] = {
    **BOOK_BY_NAME,
    **{b.name.lower(): b.code for b in BOOKS if " " not in b.name},
    "mr": "MRK", "mt": "MAT", "lk": "LUK", "jn": "JHN", "jno": "JHN", "rev": "REV",
}  # fmt: skip

_POINTER = re.compile(
    r"(?im)(?P<phrase>\bsee\s+(?:also\s+|the\s+notes?\s+)?on\b|\bsee\s+also\b"
    r"|\bwhich\s+we\s+had\s+before\b,?|\bparallel\s+place(?:\s+in\s+[A-Z][a-z]+)?\b,?"
    r"|\(\s*=|^=(?=\s))"
)
_REF = re.compile(
    r"(?P<book>[1-3]?\s?[A-Za-z]{2,10})\.?\s+(?P<ch>\d{1,3}|[ivxlc]{1,8})\b\.?"
    r"(?:\s*[:.]?\s*(?P<v1>\d{1,3})(?:\s*[-\u2013]\s*(?P<v2>\d{1,3}))?)?"
)
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}


@dataclass(frozen=True)
class Pointer:
    kind: PointerKind  # "see": an explicit pointer; "parallel": a "( = …)" list of parallels
    target: Ref


def _roman(text: str) -> int | None:
    total, prev = 0, 0
    for ch in reversed(text):
        value = _ROMAN.get(ch)
        if value is None:
            return None
        total = total - value if value < prev else total + value
        prev = max(prev, value)
    return total or None


def _book(name: str) -> str | None:
    return _DISPLAY_NAMES.get(re.sub(r"\s+", "", name).lower())


def parse_display_ref(text: str) -> tuple[Ref, int] | None:
    """The passage at the start of ``text`` ("Mt 3:1-12", "Matt. viii. 2-4", "Mr 4:14") and how
    many characters it used, or None."""
    m = _REF.match(text)
    if not m:
        return None
    book = _book(m.group("book"))
    if book is None:
        return None
    raw_ch = m.group("ch")
    chapter = int(raw_ch) if raw_ch.isdigit() else _roman(raw_ch)
    if chapter is None or not 1 <= chapter <= len(KJV_VERSES[book]):
        return None
    last = KJV_VERSES[book][chapter - 1]
    v1 = int(m.group("v1")) if m.group("v1") else None
    v2 = int(m.group("v2")) if m.group("v2") else None
    if v1 is not None and not 1 <= v1 <= last:
        v1 = v2 = None
    if v2 is not None and not (v1 or 0) < v2 <= last:
        v2 = None
    return Ref(book, chapter, v1, end_verse=v2), m.end()


def _refine(parsed: Ref, tagged: list[Ref]) -> Ref:
    """Prefer the note's tagged reference to the same book and chapter: its range is exact."""
    for ref in tagged:
        if ref.book != parsed.book or ref.chapter != parsed.chapter:
            continue
        if parsed.verse is None or ref.verse == parsed.verse:
            return ref
    return parsed


def find_pointers(text: str, refs: list[str] | None = None) -> list[Pointer]:
    """Every pointer in ``text``, in order, without duplicates. ``refs`` are the note's tagged
    references (compact strings) used to make ranges exact."""
    tagged = []
    for value in refs or []:
        try:
            tagged.append(parse_compact(value))
        except ValueError:
            continue
    out: list[Pointer] = []
    for m in _POINTER.finditer(text):
        # "( = A; B)" lists parallels. JFB sometimes breaks it after the "(", leaving "= A; B)".
        kind: PointerKind = "parallel" if m.group("phrase")[:1] in "(=" else "see"
        rest = text[m.end() :]
        # "( = A; B)" lists several parallels up to the closing bracket; the others name one.
        span = rest[: rest.find(")")] if kind == "parallel" and ")" in rest else rest[:80]
        pieces = span.split(";") if kind == "parallel" else [span]
        book_name = ""  # "Mt 8:14-17; 4:23-25": a list item without a book continues the last
        for piece in pieces:
            piece = piece.strip().lstrip("(,: ")
            found = parse_display_ref(piece)
            if found is None and book_name and piece[:1].isdigit():
                found = parse_display_ref(f"{book_name} {piece}")
            if found is None:
                continue
            book_name = piece.split()[0] if not piece[:1].isdigit() else book_name
            pointer = Pointer(kind, _refine(found[0], tagged))
            if pointer not in out:
                out.append(pointer)
    return out
