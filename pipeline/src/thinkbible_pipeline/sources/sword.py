"""Read a CrossWire SWORD commentary module (``zCom``/``zCom4``) into normalised books.

The commentaries come from CrossWire's public-domain modules (research R2a), downloaded once by
``importer.py`` as the module zip. This file never touches the network: it reads the zip.

Module layout (zip):

    mods.d/{name}.conf                       ModDrv, Version, DistributionLicense, DataPath, …
    modules/comments/zcom/{name}/ot.bzs      per block: offset and sizes in ot.bzz
    modules/comments/zcom/{name}/ot.bzv      per index entry: block, offset, size
    modules/comments/zcom/{name}/ot.bzz      zlib-compressed blocks of OSIS text
    … nt.* the same for the New Testament

Index entries follow the KJV versification: entry 0 is the module heading and 1 the testament
heading, then for each book its introduction, and for each chapter its introduction followed by
one entry per verse. A note that covers several verses is stored once and every verse in the
range points at it ("linked" entries); those become one item with ``verse`` … ``verseEnd``.
"""

from __future__ import annotations

import html
import io
import re
import struct
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import PurePosixPath

from thinkbible_core.ids import BOOKS
from thinkbible_pipeline.sources.models import (
    CommentaryChapter,
    CommentaryItem,
    CommentaryText,
    NormalizedCommentaryBook,
)
from thinkbible_pipeline.sources.refs import parse_osis_ref
from thinkbible_pipeline.sources.versification import KJV_VERSES

TESTAMENTS: dict[str, tuple[str, ...]] = {
    "ot": tuple(b.code for b in BOOKS[:39]),
    "nt": tuple(b.code for b in BOOKS[39:]),
}
_ENTRY = {"zCom": ("<IIH", 10), "zCom4": ("<III", 12)}


# Bump when the output of ``SwordCommentary.book`` changes: the importer then converts every
# commentary book again from the archived module zips. 1: first reader. 2: recovers notes the
# index lost (2026-11-16).
READER_VERSION = 2

Loc = tuple[str, int, int, int]  # (testament, block, offset in the block, size)


class SwordFormatError(ValueError):
    """The module isn't one this reader supports, or its index doesn't match the KJV scheme."""


@dataclass(frozen=True)
class ModuleConf:
    name: str
    description: str
    version: str
    license: str
    driver: str
    data_path: str
    source_type: str
    versification: str
    compress: str
    text_source: str | None
    raw: dict[str, str]


def parse_conf(text: str) -> ModuleConf:
    """A SWORD ``.conf``: ``[Name]`` then ``Key=Value`` lines (first value wins)."""
    name = ""
    raw: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]") and not name:
            name = line[1:-1]
        elif "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            raw.setdefault(key.strip(), value.strip())
    return ModuleConf(
        name=name,
        description=raw.get("Description", name),
        version=raw.get("Version", "1.0"),
        license=raw.get("DistributionLicense", ""),
        driver=raw.get("ModDrv", ""),
        data_path=raw.get("DataPath", "").removeprefix("./").rstrip("/"),
        source_type=raw.get("SourceType", ""),
        versification=raw.get("Versification", "KJV"),
        compress=raw.get("CompressType", "ZIP"),
        text_source=raw.get("TextSource"),
        raw=raw,
    )


def _expected_entries(testament: str) -> int:
    return 2 + sum(1 + len(KJV_VERSES[b]) + sum(KJV_VERSES[b]) for b in TESTAMENTS[testament])


def _index_positions() -> dict[tuple[str, int, int], tuple[str, int]]:
    """(book, chapter, verse) → (testament, entry). Chapter 0 = book intro, verse 0 = chapter."""
    out: dict[tuple[str, int, int], tuple[str, int]] = {}
    for testament, books in TESTAMENTS.items():
        i = 2
        for book in books:
            out[(book, 0, 0)] = (testament, i)
            i += 1
            for chapter, verses in enumerate(KJV_VERSES[book], 1):
                for verse in range(verses + 1):
                    out[(book, chapter, verse)] = (testament, i)
                    i += 1
    return out


_POSITIONS = _index_positions()


class SwordCommentary:
    """One commentary module, read from its zip bytes."""

    def __init__(self, zip_bytes: bytes) -> None:
        self._zip = zipfile.ZipFile(io.BytesIO(zip_bytes))
        confs = [n for n in self._zip.namelist() if n.startswith("mods.d/") and n.endswith(".conf")]
        if len(confs) != 1:
            raise SwordFormatError(f"expected one mods.d/*.conf in the module zip, found {confs}")
        self.conf = parse_conf(self._zip.read(confs[0]).decode("utf-8", "replace"))
        c = self.conf
        if c.driver not in _ENTRY:
            raise SwordFormatError(f"{c.name}: ModDrv {c.driver!r} is not zCom or zCom4")
        if c.source_type != "OSIS":
            raise SwordFormatError(f"{c.name}: SourceType {c.source_type!r} (only OSIS is read)")
        if c.versification != "KJV":
            raise SwordFormatError(f"{c.name}: versification {c.versification!r}, not KJV")
        if c.compress != "ZIP":
            raise SwordFormatError(f"{c.name}: CompressType {c.compress!r}, not ZIP")
        self._fmt, self._size = _ENTRY[c.driver]
        self._files: dict[str, bytes] = {}
        for testament in TESTAMENTS:
            for ext in ("bzs", "bzv", "bzz"):
                path = str(PurePosixPath(c.data_path) / f"{testament}.{ext}")
                try:
                    self._files[f"{testament}.{ext}"] = self._zip.read(path)
                except KeyError as e:
                    raise SwordFormatError(f"{c.name}: {path} is missing from the zip") from e
            entries = len(self._files[f"{testament}.bzv"]) // self._size
            if entries != _expected_entries(testament):
                raise SwordFormatError(
                    f"{c.name}: {testament} index has {entries} entries, the KJV scheme needs "
                    f"{_expected_entries(testament)}"
                )
        self._blocks: dict[tuple[str, int], bytes] = {}
        self._starts_cache: dict[tuple[str, int], list[int]] | None = None

    def _locate(self, book: str, chapter: int, verse: int) -> Loc:
        testament, i = _POSITIONS[(book, chapter, verse)]
        block, offset, size = struct.unpack_from(
            self._fmt, self._files[f"{testament}.bzv"], i * self._size
        )
        return testament, block, offset, size

    def _block(self, testament: str, block: int) -> bytes:
        key = (testament, block)
        if key not in self._blocks:
            start, compressed, _ = struct.unpack_from(
                "<III", self._files[f"{testament}.bzs"], block * 12
            )
            data = self._files[f"{testament}.bzz"][start : start + compressed]
            self._blocks = {key: zlib.decompress(data)}  # blocks are per book: keep one
        return self._blocks[key]

    def entry(self, book: str, chapter: int, verse: int) -> tuple[Loc, str]:
        """The raw OSIS for one index entry, with its location (equal locations = linked)."""
        loc = self._locate(book, chapter, verse)
        return loc, self.entry_at(loc)

    def _index(self, code: str) -> list[tuple[Loc, int, int, int]]:
        """The book's indexed notes in verse order: (location, chapter, first verse, last verse).

        Chapter 0 is the book introduction and verse 0 a chapter introduction. Consecutive verses
        pointing at the same location (a linked note) come back as one range.
        """
        out: list[tuple[Loc, int, int, int]] = []
        keys = [(0, 0)] + [(c, v) for c, n in enumerate(KJV_VERSES[code], 1) for v in range(n + 1)]
        for chapter, verse in keys:
            loc = self._locate(code, chapter, verse)
            if loc[3] == 0:
                continue
            last = out[-1] if out else None
            if (
                last
                and last[0] == loc
                and last[1] == chapter
                and verse > 0
                and last[3] == verse - 1
            ):
                out[-1] = (loc, chapter, last[2], verse)
            else:
                out.append((loc, chapter, verse, verse))
        return out

    def _recover(
        self, code: str, index: list[tuple[Loc, int, int, int]]
    ) -> list[tuple[int, int, CommentaryText]]:
        """Text in the book's blocks that no index entry points at (research R2a).

        Some modules (JFB above all) hold notes in their compressed blocks that the verse index
        lost. Each gap between two indexed notes is split at the commentator's verse numbers
        ("5. they all brought us…", "Verse 5") and every piece goes to that verse of the chapter
        the gap follows; text before the first number continues the preceding note.
        Returns (chapter, verse, text) pieces; verse 0 is the chapter introduction.
        """
        pieces: list[tuple[int, int, CommentaryText]] = []
        by_block: dict[tuple[str, int], list[tuple[int, int, int, int]]] = {}
        for (testament, block, offset, size), chapter, _first, last in index:
            by_block.setdefault((testament, block), []).append((offset, size, chapter, last))
        for (testament, block), spans in by_block.items():
            data = self._block(testament, block)
            starts = self._starts(testament, block)  # every indexed note in the block, any book
            spans.sort()
            for offset, size, chapter, last in spans:
                gap_start = offset + size
                gap_end = next((s for s in starts if s >= gap_start), len(data))
                if gap_end <= gap_start:
                    continue
                verse = last
                for chunk in _PARA_SPLIT.split(data[gap_start:gap_end].decode("utf-8", "replace")):
                    note = osis_to_text(chunk)
                    if note is None:
                        continue
                    numbered = _VERSE_NUMBER.match(note.text)
                    if numbered and chapter > 0:
                        n = int(numbered.group(1) or numbered.group(2))
                        if 1 <= n <= KJV_VERSES[code][chapter - 1]:
                            verse = n
                    pieces.append((chapter, verse, note))
        return pieces

    def _starts(self, testament: str, block: int) -> list[int]:
        """Sorted start offsets of every indexed note in a block (cached per module)."""
        if self._starts_cache is None:
            cache: dict[tuple[str, int], set[int]] = {}
            for t in TESTAMENTS:
                bzv = self._files[f"{t}.bzv"]
                for i in range(len(bzv) // self._size):
                    blk, offset, size = struct.unpack_from(self._fmt, bzv, i * self._size)
                    if size:
                        cache.setdefault((t, blk), set()).add(offset)
            self._starts_cache = {k: sorted(v) for k, v in cache.items()}
        return self._starts_cache.get((testament, block), [])

    def book(self, code: str) -> NormalizedCommentaryBook | None:
        """All notes on one book, or ``None`` if the module has nothing on it."""
        index = self._index(code)
        book_intro: CommentaryText | None = None
        intros: dict[int, CommentaryText] = {}
        items: dict[int, list[CommentaryItem]] = {}
        for loc, chapter, first, last in index:
            note = osis_to_text(self.entry_at(loc))
            if note is None:
                continue
            if chapter == 0:
                book_intro = note
            elif first == 0:
                intros[chapter] = note
            else:
                items.setdefault(chapter, []).append(
                    CommentaryItem(
                        verse=first,
                        verse_end=last if last != first else None,
                        text=note.text,
                        refs=note.refs,
                    )
                )
        for chapter, verse, note in self._recover(code, index):
            if chapter == 0:
                book_intro = _join(book_intro, note)
            elif verse == 0:
                intros[chapter] = _join(intros.get(chapter), note)
            else:
                _attach(items.setdefault(chapter, []), verse, note)
        chapters = [
            CommentaryChapter(
                number=number,
                introduction=intros.get(number),
                items=sorted(items.get(number, []), key=lambda i: i.verse),
            )
            for number in range(1, len(KJV_VERSES[code]) + 1)
            if items.get(number) or intros.get(number)
        ]
        if not chapters:
            return None
        return NormalizedCommentaryBook(book=code, introduction=book_intro, chapters=chapters)

    def entry_at(self, loc: Loc) -> str:
        testament, block, offset, size = loc
        if size == 0:
            return ""
        return self._block(testament, block)[offset : offset + size].decode("utf-8", "replace")


# Paragraph boundaries in OSIS, and the commentators' verse numbers: JFB "5. …" / "2-3. …",
# Clarke "Verse 5" / "Verses 5-7".
_PARA_SPLIT = re.compile(r'<div\b[^>]*type="x-p"[^>]*/>')
_VERSE_NUMBER = re.compile(r"^(?:(\d{1,3})(?:\s*[-,]\s*\d{1,3})?\.\s|Verses? (\d{1,3})\b)")


def _join(note: CommentaryText | None, more: CommentaryText) -> CommentaryText:
    if note is None:
        return more
    if more.text in note.text:
        return note
    refs = note.refs + [r for r in more.refs if r not in note.refs]
    return CommentaryText(text=f"{note.text}\n\n{more.text}", refs=refs)


def _attach(items: list[CommentaryItem], verse: int, note: CommentaryText) -> None:
    """Add a recovered note to the item covering ``verse``, or as a new item for it."""
    for item in items:
        if item.verse <= verse <= (item.verse_end or item.verse):
            joined = _join(item, note)
            item.text, item.refs = joined.text, joined.refs
            return
    items.append(CommentaryItem(verse=verse, text=note.text, refs=note.refs))


# --- OSIS → text ---

_REF_TAG = re.compile(r'<reference\b[^>]*?osisRef="([^"]*)"[^>]*>')
_NOTE = re.compile(r"<note\b[^>]*>.*?</note>", re.S)
_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.S)
_MILESTONE = re.compile(
    r"<div\b[^>]*type=\"x-milestone\"[^>]*/>|<milestone\b[^>]*/>|</?chapter\b[^>]*>"
)
_PARAGRAPH = re.compile(r"</?(?:div|lg|p)\b[^>]*>")  # after milestones are gone
_LINE = re.compile(r"<l\b[^>]*/?>|</l>|<lb\b[^>]*/?>")
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\r\f\v]+")
_PARA_MARK = "\x1e"  # ASCII record separator: never in the text
_LINE_MARK = "\x1f"  # ASCII unit separator


def osis_to_text(raw: str) -> CommentaryText | None:
    """One entry's OSIS → plain text with paragraphs (blank lines) and its references.

    Kept: words, titles (as their own paragraph), paragraph and poetry line breaks, and the
    text of every ``<reference>``. Dropped: formatting (bold, italics), milestones and the
    publisher's footnotes (``<note>``). Returns ``None`` for an entry with no words.
    """
    refs: list[str] = []
    for value in _REF_TAG.findall(raw):
        for ref in parse_osis_ref(html.unescape(value)):
            if ref not in refs:
                refs.append(ref)
    text = _NOTE.sub(" ", raw)
    text = _MILESTONE.sub(" ", text)
    text = _TITLE.sub(lambda m: f"{_PARA_MARK}{m.group(1)}{_PARA_MARK}", text)
    text = _PARAGRAPH.sub(_PARA_MARK, text)
    text = _LINE.sub(_LINE_MARK, text)
    text = html.unescape(_TAG.sub("", text))
    paragraphs = []
    for para in text.replace("\n", " ").split(_PARA_MARK):
        lines = [_SPACES.sub(" ", line).strip() for line in para.split(_LINE_MARK)]
        joined = "\n".join(line for line in lines if line)
        if joined:
            paragraphs.append(joined)
    body = "\n\n".join(paragraphs)
    if not re.search(r"\w", body):
        return None
    return CommentaryText(text=body, refs=refs)
