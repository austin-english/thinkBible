"""Turn Free Use Bible API chapter JSON into normalised translation books (R2, data-model §3).

Kept: verses, headings, psalm titles, paragraph breaks, poetry lines with their indent and
footnotes. Dropped: audio links, navigation links, red-letter markup and other presentation-only
fields. Commentaries come from CrossWire modules instead and are read by ``sword.py``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from thinkbible_pipeline.sources.models import (
    BreakItem,
    Footnote,
    HeadingItem,
    Line,
    NormalizedTranslationBook,
    SubtitleItem,
    TranslationChapter,
    TranslationItem,
    VerseItem,
)

Json = dict[str, Any]

_SPACES = re.compile(r"\s+")


class NormalizeError(ValueError):
    pass


def _join(pieces: Iterable[str]) -> str:
    """Join text pieces with single spaces. The API's pieces never carry edge spaces."""
    return _SPACES.sub(" ", " ".join(p for p in pieces if p)).strip()


def _pieces(content: list[Any], where: str) -> tuple[list[Line], list[int], bool]:
    """Verse-style content → display lines, footnote IDs, and whether it has poetry/breaks."""
    lines: list[Line] = []
    prose: list[str] = []
    note_ids: list[int] = []
    has_lines = False

    def flush_prose() -> None:
        if prose:
            lines.append(Line(text=_join(prose), indent=0))
            prose.clear()

    for piece in content:
        if isinstance(piece, str):
            prose.append(piece)
        elif "noteId" in piece:
            note_ids.append(int(piece["noteId"]))
        elif piece.get("lineBreak"):
            has_lines = True
            flush_prose()
        elif "text" in piece:
            if "poem" in piece:
                has_lines = True
                flush_prose()
                lines.append(Line(text=_join([piece["text"]]), indent=int(piece["poem"])))
            else:  # e.g. {"text", "wordsOfJesus"}: keep the words, drop the markup
                prose.append(piece["text"])
        else:
            raise NormalizeError(f"unknown verse content {piece!r} in {where}")
    flush_prose()
    return lines, note_ids, has_lines


def _verse(raw: Json) -> VerseItem:
    lines, note_ids, has_lines = _pieces(raw.get("content", []), f"verse {raw.get('number')}")
    return VerseItem(
        number=int(raw["number"]),
        text=_join(line.text for line in lines),
        lines=lines if has_lines else None,
        note_ids=note_ids,
    )


def _subtitle(raw: Json) -> SubtitleItem:
    """A psalm title. Same pieces as a verse; shown before verse 1."""
    lines, note_ids, _ = _pieces(raw.get("content", []), "a psalm title")
    return SubtitleItem(text=_join(line.text for line in lines), note_ids=note_ids)


def normalize_translation_chapter(raw: Json) -> TranslationChapter:
    """One ``/api/{translation}/{BOOK}/{ch}.json`` response → a normalised chapter."""
    chapter = raw["chapter"]
    items: list[TranslationItem] = []
    for item in chapter["content"]:
        kind = item["type"]
        if kind == "verse":
            items.append(_verse(item))
        elif kind == "heading":
            items.append(HeadingItem(text=_join(str(p) for p in item.get("content", []))))
        elif kind == "hebrew_subtitle":
            items.append(_subtitle(item))
        elif kind == "line_break":
            marker = item.get("paragraph")
            items.append(BreakItem(paragraph=marker is not None, marker=marker))
        else:
            raise NormalizeError(f"unknown chapter content type {kind!r}")
    footnotes = [
        Footnote(
            note_id=int(f["noteId"]),
            text=_join([f["text"]]),
            chapter=int(f["reference"]["chapter"]),
            verse=int(f["reference"]["verse"]),
        )
        for f in chapter.get("footnotes", [])
    ]
    return TranslationChapter(number=int(chapter["number"]), items=items, footnotes=footnotes)


def normalize_translation_book(book: str, chapters: Iterable[Json]) -> NormalizedTranslationBook:
    normalized = sorted(
        (normalize_translation_chapter(c) for c in chapters), key=lambda c: c.number
    )
    return NormalizedTranslationBook(book=book, chapters=normalized)
