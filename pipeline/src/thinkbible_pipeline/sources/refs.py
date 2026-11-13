"""Scripture references in commentary notes: OSIS ``osisRef`` values → compact USFM strings.

CrossWire's modules tag every reference, e.g. ``<reference osisRef="Matt.12.9-Matt.12.21">``.
We store them as ``MAT 12:9-21`` so later stages (cross-references, gathering excerpts) don't
have to parse prose like "see on Mt 12". Forms written out:

    MAT 12        a whole chapter
    MAT 12:9      one verse
    MAT 12:9-21   verses in one chapter
    MAT 12:9-13:2 across chapters

Commentators' tagging is mostly standard OSIS (``Ps.42.7``), but Clarke uses older
abbreviations (``Psa``, ``Joh``, ``Mat``) and some of Henry's lists are shorthand that carries
the book and chapter forward (``Pr.10.19 11.12 28`` = Proverbs 10:19, 11:12, 11:28). References to
books outside the 66 (the Apocrypha) and anything that doesn't parse are dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from thinkbible_pipeline.sources.versification import KJV_VERSES

# Every spelling seen in the JFB, MHC and Clarke modules, by USFM code. OSIS names first.
_ALIASES: dict[str, tuple[str, ...]] = {
    "GEN": ("Gen", "Ge"), "EXO": ("Exod", "Exo", "Ex"), "LEV": ("Lev", "Le"),
    "NUM": ("Num", "Nu"), "DEU": ("Deut", "Deu", "De"), "JOS": ("Josh", "Jos"),
    "JDG": ("Judg", "Jdg"), "RUT": ("Ruth", "Rut"), "1SA": ("1Sam", "1Sa"),
    "2SA": ("2Sam", "2Sa"), "1KI": ("1Kgs", "1Ki"), "2KI": ("2Kgs", "2Ki"),
    "1CH": ("1Chr", "1Ch"), "2CH": ("2Chr", "2Ch"), "EZR": ("Ezra", "Ezr"),
    "NEH": ("Neh", "Ne"), "EST": ("Esth", "Est"), "JOB": ("Job",), "PSA": ("Ps", "Psa"),
    "PRO": ("Prov", "Pro", "Pr"), "ECC": ("Eccl", "Ecc"), "SNG": ("Song", "Sol", "Sng"),
    "ISA": ("Isa",), "JER": ("Jer",), "LAM": ("Lam", "La"), "EZK": ("Ezek", "Eze"),
    "DAN": ("Dan", "Da"), "HOS": ("Hos", "Ho"), "JOL": ("Joel", "Joe"),
    "AMO": ("Amos", "Amo", "Am"), "OBA": ("Obad", "Oba"), "JON": ("Jonah", "Jon"),
    "MIC": ("Mic",), "NAM": ("Nah",), "HAB": ("Hab",), "ZEP": ("Zeph", "Zep"), "HAG": ("Hag",),
    "ZEC": ("Zech", "Zec", "Zac"), "MAL": ("Mal",), "MAT": ("Matt", "Mat", "Mt"),
    "MRK": ("Mark", "Mar", "Mk"), "LUK": ("Luke", "Luk", "Lu"), "JHN": ("John", "Joh"),
    "ACT": ("Acts", "Act", "Ac"), "ROM": ("Rom",), "1CO": ("1Cor",), "2CO": ("2Cor",),
    "GAL": ("Gal",), "EPH": ("Eph",), "PHP": ("Phil", "Phi", "Php"), "COL": ("Col",),
    "1TH": ("1Thess", "1Thes"), "2TH": ("2Thess", "2Thes"), "1TI": ("1Tim", "1Ti"),
    "2TI": ("2Tim", "2Ti"), "TIT": ("Titus", "Tit"), "PHM": ("Phlm", "Plm"), "HEB": ("Heb",),
    "JAS": ("Jas", "Jam"), "1PE": ("1Pet", "1Pe"), "2PE": ("2Pet", "2Pe"),
    "1JN": ("1John", "1Jn", "1Jo"), "2JN": ("2John", "2Jn"), "3JN": ("3John", "3Jn"),
    "JUD": ("Jude", "Jde"), "REV": ("Rev",),
}  # fmt: skip
BOOK_BY_NAME: dict[str, str] = {
    name.lower(): code for code, names in _ALIASES.items() for name in names
}

_POINT = re.compile(r"^(?:([1-3]?[A-Za-z]+)\.?)?(?:(\d+)(?:\.(\d+))?)?$")


@dataclass(frozen=True)
class _Point:
    book: str
    chapter: int
    verse: int | None


def _valid(p: _Point) -> bool:
    chapters = KJV_VERSES[p.book]
    if not 1 <= p.chapter <= len(chapters):
        return False
    return p.verse is None or 1 <= p.verse <= chapters[p.chapter - 1]


def _point(token: str, book: str | None, chapter: int | None) -> _Point | None:
    """``Matt.12.9``, ``Matt.12``, ``12.9`` (book carried), ``9`` (book and chapter carried)."""
    m = _POINT.match(token.removeprefix("Bible:"))
    if not m or not (m.group(1) or m.group(2)):
        return None
    name, a, b = m.group(1), m.group(2), m.group(3)
    if name is not None:
        code = BOOK_BY_NAME.get(name.lower())
        if code is None or a is None:
            return None  # Apocrypha, unknown abbreviation, or a bare book name
        return _Point(code, int(a), int(b) if b else None)
    if book is None or a is None:
        return None
    if b is not None:
        return _Point(book, int(a), int(b))
    if chapter is not None:  # a bare number continues a verse list: "11.12 28" → 11:28
        return _Point(book, chapter, int(a))
    return _Point(book, int(a), None)


def _before(a: _Point, b: _Point) -> bool:
    return (a.chapter, a.verse or 0) < (b.chapter, b.verse or 0)


def _format(start: _Point, end: _Point | None) -> str:
    out = f"{start.book} {start.chapter}"
    if start.verse is not None:
        out += f":{start.verse}"
    if end is None or end == start:
        return out
    if end.chapter == start.chapter and end.verse is not None and start.verse is not None:
        return f"{out}-{end.verse}"
    tail = f"{end.chapter}" + (f":{end.verse}" if end.verse is not None else "")
    return f"{out}-{tail}"


def parse_osis_ref(value: str) -> list[str]:
    """One ``osisRef`` attribute (possibly a space-separated list) → compact references."""
    out: list[str] = []
    book: str | None = None
    chapter: int | None = None
    pending_book: str | None = None  # "2Pe 1.16": a bare book name, then its chapter and verse
    for token in value.split():
        if token.lower() in BOOK_BY_NAME:
            pending_book = BOOK_BY_NAME[token.lower()]
            chapter = None
            continue
        if pending_book is not None:
            book, pending_book = pending_book, None
        left, _, right = token.partition("-")
        start = _point(left, book, chapter)
        if start is None or not _valid(start):
            continue
        end = None
        if right:
            end = _point(right, start.book, start.chapter if start.verse is not None else None)
            if end is None or end.book != start.book or not _valid(end) or _before(end, start):
                end = None
        book, chapter = start.book, start.chapter
        if end is not None:
            chapter = end.chapter
        ref = _format(start, end)
        if ref not in out:
            out.append(ref)
    return out
