"""Split a book into reading sections (research R5, FR-004). Deterministic: no model calls.

Per chapter:

1. Each BSB heading starts a candidate section. A chapter with no heading at verse 1 starts with
   a piece of the previous heading, titled "{heading} (cont.)". Sections never cross chapters.
2. Candidates shorter than 3 verses merge into the section before them, which they usually
   finish (Jesus' answer about patches and wineskins finishes the fasting question, Mark
   2:18-22; Judas going out finishes the anointing, Mark 14:1-11). They merge into the next one
   instead when they open a Henry division that the next one doesn't (the piece starts a new
   passage), or when they are first in the chapter. The merged section takes the longer piece's
   title. (Until 2026-11-18 short pieces merged forward, gluing Mark 2:21-22 to the Sabbath.)
3. Sections longer than 12 verses split at Matthew Henry's division start nearest the middle;
   without one, at the BSB paragraph break nearest the middle; without one, at the middle verse.
   Both pieces keep at least 3 verses. Later pieces are titled "{heading} (cont.)" with
   ``titleSource: "split"``, so the scorecard can flag them for a better title.

Merging runs before splitting so a merge can't leave a section over 12 verses. Ranges cover
every verse of the KJV versification (so KJV-only verses such as Mark 7:16 belong to a section
even though the BSB omits them). IDs are ``{book}-{chapter}-{firstVerse}``, e.g. ``mrk-1-1``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.drafts.models import SectionMapEntry
from thinkbible_pipeline.sources.models import (
    BreakItem,
    HeadingItem,
    NormalizedCommentaryBook,
    NormalizedTranslationBook,
    VerseItem,
)
from thinkbible_pipeline.sources.versification import KJV_VERSES

MIN_VERSES = 3
MAX_VERSES = 12


@dataclass
class _Piece:
    start: int
    end: int
    title: str
    split: bool = False  # the title is a provisional "(cont.)"

    @property
    def length(self) -> int:
        return self.end - self.start + 1


@dataclass
class _Chapter:
    number: int
    last_verse: int
    headings: dict[int, str] = field(default_factory=dict)  # first verse → heading
    paragraphs: set[int] = field(default_factory=set)  # verses that start a paragraph
    henry: set[int] = field(default_factory=set)  # Henry division start verses


def _chapters(
    book: str, bsb: NormalizedTranslationBook, henry: NormalizedCommentaryBook | None
) -> list[_Chapter]:
    henry_starts: dict[int, set[int]] = {}
    if henry is not None:
        for hc in henry.chapters:
            henry_starts[hc.number] = {i.verse for i in hc.items}
    by_number = {c.number: c for c in bsb.chapters}
    out: list[_Chapter] = []
    # The chapters the BSB has (a missing chapter is a snapshot error `sources check` reports),
    # each covering every verse of the KJV versification.
    for number in sorted(n for n in by_number if 1 <= n <= len(KJV_VERSES[book])):
        last = KJV_VERSES[book][number - 1]
        ch = _Chapter(number=number, last_verse=last, henry=henry_starts.get(number, set()))
        source = by_number.get(number)
        pending: str | None = None
        paragraph = False
        for item in source.items if source else []:
            if isinstance(item, HeadingItem):
                pending = item.text  # stacked headings: the last (most specific) wins
            elif isinstance(item, BreakItem):
                paragraph = paragraph or item.paragraph
            elif isinstance(item, VerseItem):
                if pending is not None:
                    ch.headings[item.number] = pending
                    ch.paragraphs.add(item.number)
                    pending = None
                if paragraph:
                    ch.paragraphs.add(item.number)
                    paragraph = False
        ch.paragraphs.add(1)
        out.append(ch)
    return out


def _opens_next(p: _Piece, nxt: _Piece, henry: set[int]) -> bool:
    """Whether a short piece starts a passage that runs on into the next piece (Henry's view)."""
    return p.start in henry and nxt.start not in henry


def _merge_short(pieces: list[_Piece], henry: set[int] | None = None) -> list[_Piece]:
    pieces = list(pieces)
    henry = henry or set()
    i = 0
    while len(pieces) > 1 and i < len(pieces):
        p = pieces[i]
        if p.length >= MIN_VERSES:
            i += 1
            continue
        forward = i == 0 or (i + 1 < len(pieces) and _opens_next(p, pieces[i + 1], henry))
        if forward:  # into the next section
            nxt = pieces[i + 1]
            keep = nxt if nxt.length >= p.length else p
            pieces[i : i + 2] = [_Piece(p.start, nxt.end, keep.title, keep.split)]
        else:  # the last one in the chapter: into the previous section
            prev = pieces[i - 1]
            keep = prev if prev.length >= p.length else p
            pieces[i - 1 : i + 1] = [_Piece(prev.start, p.end, keep.title, keep.split)]
            i -= 1
    return pieces


def _cont(title: str) -> str:
    return title if title.endswith(" (cont.)") else f"{title} (cont.)"


def _split_long(piece: _Piece, ch: _Chapter) -> list[_Piece]:
    if piece.length <= MAX_VERSES:
        return [piece]
    # A split at verse s gives start..s-1 and s..end, each at least MIN_VERSES long.
    allowed = range(piece.start + MIN_VERSES, piece.end - MIN_VERSES + 2)
    middle = (piece.start + piece.end + 1) / 2
    at = None
    for candidates in (ch.henry, ch.paragraphs):
        inside = [s for s in allowed if s in candidates]
        if inside:
            at = min(inside, key=lambda s: (abs(s - middle), s))
            break
    if at is None:
        at = int(middle)
    first = _Piece(piece.start, at - 1, piece.title, piece.split)
    second = _Piece(at, piece.end, _cont(piece.title), True)
    return _split_long(first, ch) + _split_long(second, ch)


def build_sections(
    book: str, bsb: NormalizedTranslationBook, henry: NormalizedCommentaryBook | None
) -> list[SectionMapEntry]:
    """The section map for ``book`` (a USFM code) from its BSB headings and Henry's divisions."""
    info = resolve_book(book)
    slug = info.code.lower()
    entries: list[SectionMapEntry] = []
    carried: str | None = None  # the last heading seen, for chapters that start mid-section
    for ch in _chapters(info.code, bsb, henry):
        starts = sorted(ch.headings)
        pieces: list[_Piece] = []
        if not starts or starts[0] != 1:
            title = _cont(carried) if carried else f"{info.name} {ch.number}"
            first_end = (starts[0] - 1) if starts else ch.last_verse
            pieces.append(_Piece(1, first_end, title, split=True))
        for i, s in enumerate(starts):
            end = starts[i + 1] - 1 if i + 1 < len(starts) else ch.last_verse
            pieces.append(_Piece(s, end, ch.headings[s]))
        if starts:
            carried = ch.headings[starts[-1]]
        for piece in _merge_short(pieces, ch.henry):
            for part in _split_long(piece, ch):
                entries.append(
                    SectionMapEntry(
                        id=f"{slug}-{ch.number}-{part.start}",
                        chapter=ch.number,
                        verse_start=part.start,
                        verse_end=part.end,
                        title=part.title,
                        title_source="split" if part.split else "bsb-heading",
                        henry_divisions=sorted(v for v in ch.henry if part.start <= v <= part.end),
                    )
                )
    return entries
