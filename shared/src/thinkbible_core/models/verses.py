"""VerseText: one translation's text of one book (content/schema/verses.schema.json)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from thinkbible_core.models._base import ContractModel, PackVersion, TranslationId, Verse
from thinkbible_core.models.pack import Book


class TranslationInfo(ContractModel):
    id: TranslationId
    name: str
    abbreviation: Annotated[str, StringConstraints(max_length=8)]


class PoetryLine(ContractModel):
    text: str
    indent: Annotated[int, Field(ge=0, le=4)]


class VerseEntry(ContractModel):
    number: Verse
    text: Annotated[str, StringConstraints(min_length=1)]
    paragraph_start: bool | None = None
    lines: list[PoetryLine] | None = None


class Chapter(ContractModel):
    number: Annotated[int, Field(ge=1)]
    verses: Annotated[list[VerseEntry], Field(min_length=1)]


class OmittedVerse(ContractModel):
    chapter: Annotated[int, Field(ge=1)]
    verse: Verse


class VerseText(ContractModel):
    format_version: Literal[1]
    book: Book
    translation: TranslationInfo
    pack_version: PackVersion
    chapters: Annotated[list[Chapter], Field(min_length=1)]
    omitted_verses: list[OmittedVerse]

    def verse_set(self) -> set[tuple[int, int]]:
        """All (chapter, verse) pairs present in this translation."""
        return {(c.number, v.number) for c in self.chapters for v in c.verses}
