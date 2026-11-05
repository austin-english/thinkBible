"""Book codes and permanent content IDs.

IDs (research R13):
- section   ``{book}-{chapter}-{startVerse}``, e.g. ``mrk-1-1``
- key idea  ``{section}-k{n}``,                 e.g. ``mrk-1-1-k3``
- question  ``{section}-q{n}``,                 e.g. ``mrk-1-1-q4``

``book`` is the lowercase USFM code. IDs are permanent: never change this format in a way that
re-keys existing content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class BookInfo:
    code: str  # USFM, e.g. "MRK"
    name: str  # English name, e.g. "Mark"
    order: int  # canonical order, 1-66

    @property
    def slug(self) -> str:
        """Lowercase USFM code used in IDs and paths, e.g. "mrk"."""
        return self.code.lower()


_BOOKS: tuple[tuple[str, str], ...] = (
    ("GEN", "Genesis"), ("EXO", "Exodus"), ("LEV", "Leviticus"), ("NUM", "Numbers"),
    ("DEU", "Deuteronomy"), ("JOS", "Joshua"), ("JDG", "Judges"), ("RUT", "Ruth"),
    ("1SA", "1 Samuel"), ("2SA", "2 Samuel"), ("1KI", "1 Kings"), ("2KI", "2 Kings"),
    ("1CH", "1 Chronicles"), ("2CH", "2 Chronicles"), ("EZR", "Ezra"), ("NEH", "Nehemiah"),
    ("EST", "Esther"), ("JOB", "Job"), ("PSA", "Psalms"), ("PRO", "Proverbs"),
    ("ECC", "Ecclesiastes"), ("SNG", "Song of Songs"), ("ISA", "Isaiah"), ("JER", "Jeremiah"),
    ("LAM", "Lamentations"), ("EZK", "Ezekiel"), ("DAN", "Daniel"), ("HOS", "Hosea"),
    ("JOL", "Joel"), ("AMO", "Amos"), ("OBA", "Obadiah"), ("JON", "Jonah"), ("MIC", "Micah"),
    ("NAM", "Nahum"), ("HAB", "Habakkuk"), ("ZEP", "Zephaniah"), ("HAG", "Haggai"),
    ("ZEC", "Zechariah"), ("MAL", "Malachi"),
    ("MAT", "Matthew"), ("MRK", "Mark"), ("LUK", "Luke"), ("JHN", "John"), ("ACT", "Acts"),
    ("ROM", "Romans"), ("1CO", "1 Corinthians"), ("2CO", "2 Corinthians"),
    ("GAL", "Galatians"), ("EPH", "Ephesians"), ("PHP", "Philippians"), ("COL", "Colossians"),
    ("1TH", "1 Thessalonians"), ("2TH", "2 Thessalonians"), ("1TI", "1 Timothy"),
    ("2TI", "2 Timothy"), ("TIT", "Titus"), ("PHM", "Philemon"), ("HEB", "Hebrews"),
    ("JAS", "James"), ("1PE", "1 Peter"), ("2PE", "2 Peter"), ("1JN", "1 John"),
    ("2JN", "2 John"), ("3JN", "3 John"), ("JUD", "Jude"), ("REV", "Revelation"),
)  # fmt: skip

BOOKS: tuple[BookInfo, ...] = tuple(
    BookInfo(code=code, name=name, order=i + 1) for i, (code, name) in enumerate(_BOOKS)
)
_BY_CODE = {b.code: b for b in BOOKS}

# Extra spellings accepted on the command line, keyed by normalised name.
_ALIASES = {
    "psalm": "PSA",
    "songofsolomon": "SNG",
    "song": "SNG",
    "canticles": "SNG",
    "revelations": "REV",
}


def _norm(name: str) -> str:
    return re.sub(r"[\s._-]+", "", name).lower()


_BY_NAME = {_norm(b.name): b for b in BOOKS}


class UnknownBookError(ValueError):
    pass


def resolve_book(name_or_code: str) -> BookInfo:
    """Resolve "mark", "Mark", "MRK", "mrk", "1 samuel" or "1SA" to a BookInfo."""
    raw = name_or_code.strip()
    if raw.upper() in _BY_CODE:
        return _BY_CODE[raw.upper()]
    key = _norm(raw)
    if key in _BY_NAME:
        return _BY_NAME[key]
    if key in _ALIASES:
        return _BY_CODE[_ALIASES[key]]
    raise UnknownBookError(f"unknown book: {name_or_code!r}")


def book_by_slug(slug: str) -> BookInfo:
    return resolve_book(slug.upper())


# --- content IDs -------------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^(?P<book>[0-9a-z]{3})-(?P<chapter>[0-9]{1,3})-(?P<verse>[0-9]{1,3})$")
_ITEM_RE = re.compile(
    r"^(?P<section>[0-9a-z]{3}-[0-9]{1,3}-[0-9]{1,3})-(?P<kind>[kq])(?P<n>[0-9]{1,3})$"
)


def section_id(book: str | BookInfo, chapter: int, start_verse: int) -> str:
    info = book if isinstance(book, BookInfo) else resolve_book(book)
    return f"{info.slug}-{chapter}-{start_verse}"


def key_idea_id(section: str, n: int) -> str:
    _check_section_id(section)
    return f"{section}-k{n}"


def question_id(section: str, n: int) -> str:
    _check_section_id(section)
    return f"{section}-q{n}"


@dataclass(frozen=True)
class SectionIdParts:
    book: str  # lowercase USFM
    chapter: int
    start_verse: int


@dataclass(frozen=True)
class ItemIdParts:
    section: str
    kind: Literal["k", "q"]
    n: int


def parse_section_id(value: str) -> SectionIdParts:
    m = _SECTION_RE.match(value)
    if not m:
        raise ValueError(f"not a section id: {value!r}")
    return SectionIdParts(m["book"], int(m["chapter"]), int(m["verse"]))


def parse_item_id(value: str) -> ItemIdParts:
    m = _ITEM_RE.match(value)
    if not m:
        raise ValueError(f"not a key idea or question id: {value!r}")
    kind: Literal["k", "q"] = "k" if m["kind"] == "k" else "q"
    return ItemIdParts(m["section"], kind, int(m["n"]))


def _check_section_id(value: str) -> None:
    parse_section_id(value)
