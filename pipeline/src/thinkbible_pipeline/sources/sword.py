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

    def _locate(self, book: str, chapter: int, verse: int) -> tuple[str, int, int, int]:
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

    def entry(self, book: str, chapter: int, verse: int) -> tuple[tuple[str, int, int, int], str]:
        """The raw OSIS for one index entry, with its location (equal locations = linked)."""
        loc = self._locate(book, chapter, verse)
        testament, block, offset, size = loc
        if size == 0:
            return loc, ""
        raw = self._block(testament, block)[offset : offset + size]
        return loc, raw.decode("utf-8", "replace")

    def book(self, code: str) -> NormalizedCommentaryBook | None:
        """All notes on one book, or ``None`` if the module has nothing on it."""
        chapters: list[CommentaryChapter] = []
        for number, verses in enumerate(KJV_VERSES[code], 1):
            items: list[CommentaryItem] = []
            previous: tuple[str, int, int, int] | None = None
            for verse in range(1, verses + 1):
                loc, raw = self.entry(code, number, verse)
                if loc[3] == 0:
                    previous = None
                    continue
                if loc == previous and items:
                    items[-1].verse_end = verse
                    continue
                previous = loc
                note = osis_to_text(raw)
                if note is not None:
                    items.append(CommentaryItem(verse=verse, text=note.text, refs=note.refs))
            intro = osis_to_text(self.entry(code, number, 0)[1])
            if items or intro:
                chapters.append(CommentaryChapter(number=number, introduction=intro, items=items))
        if not chapters:
            return None
        intro = osis_to_text(self.entry(code, 0, 0)[1])
        return NormalizedCommentaryBook(book=code, introduction=intro, chapters=chapters)


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
