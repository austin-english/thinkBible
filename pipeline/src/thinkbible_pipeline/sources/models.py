"""Source snapshot entities (data-model.md §3): the manifest and the normalised books."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from thinkbible_pipeline.jsonio import JsonModel

SourceKind = Literal["translation", "commentary"]


class BookFile(JsonModel):
    file: str  # path in the local cache, relative to content/sources/
    s3_key: str  # write-once object key, e.g. snapshots/2026-11-05/bsb/MRK.json
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    bytes: Annotated[int, Field(ge=0)]
    retrieved_at: str
    snapshot_id: str


class ModuleFile(BookFile):
    """The upstream file a source was converted from, archived next to its books (CrossWire
    module zips), so the snapshot never depends on the upstream site again."""

    name: str  # e.g. "JFB"
    version: str  # the module's Version, e.g. "3.0"
    url: str  # where it was downloaded from


class SourceEntry(JsonModel):
    kind: SourceKind
    api_id: str  # the upstream ID: HelloAO translation ID, or CrossWire module name
    name: str
    license: str
    license_url: str | None = None
    upstream_sha256: str | None = None
    tradition: str | None = None  # commentaries only, e.g. "Wesleyan (Methodist)"
    # Which upstream edition the books were made from, e.g. "helloao:BSB" or "crosswire:JFB@3.0".
    # When it changes, every book of the source is imported again.
    origin: str | None = None
    module: ModuleFile | None = None
    books: dict[str, BookFile] = Field(default_factory=dict)  # keyed by USFM code

    def files(self) -> list[tuple[str, BookFile]]:
        """Every file of this source: its books, then the archived module if there is one."""
        out: list[tuple[str, BookFile]] = sorted(self.books.items())
        if self.module is not None:
            out.append(("module", self.module))
        return out


class SourceManifest(JsonModel):
    bucket: str
    api_version: str
    sources: dict[str, SourceEntry] = Field(default_factory=dict)


# --- Normalised translation book ({tr}/{BOOK}.json) ---


class HeadingItem(JsonModel):
    type: Literal["heading"] = "heading"
    text: str


class SubtitleItem(JsonModel):
    """A psalm's title ("A Psalm of David, when he fled ..."): part of the text, before verse 1."""

    type: Literal["subtitle"] = "subtitle"
    text: str
    note_ids: list[int] = Field(default_factory=list)


class Line(JsonModel):
    """One display line of a verse that contains poetry or a line break."""

    text: str
    indent: Annotated[int, Field(ge=0)] = 0  # 0 = prose, 1+ = the source's poetry indent level


class VerseItem(JsonModel):
    type: Literal["verse"] = "verse"
    number: Annotated[int, Field(ge=1)]
    text: str  # the whole verse as one string, pieces joined by single spaces
    lines: list[Line] | None = None  # only when the verse has poetry or a line break
    note_ids: list[int] = Field(default_factory=list)


class BreakItem(JsonModel):
    """A paragraph or line break between verses."""

    type: Literal["break"] = "break"
    paragraph: bool = True
    marker: str | None = None  # the source's USFM-style marker, e.g. "p" or "m"


TranslationItem = Annotated[
    HeadingItem | SubtitleItem | VerseItem | BreakItem, Field(discriminator="type")
]


class Footnote(JsonModel):
    note_id: int
    text: str
    chapter: int
    verse: int


class TranslationChapter(JsonModel):
    number: Annotated[int, Field(ge=1)]
    items: list[TranslationItem]
    footnotes: list[Footnote] = Field(default_factory=list)

    def verses(self) -> list[VerseItem]:
        return [i for i in self.items if isinstance(i, VerseItem)]


class NormalizedTranslationBook(JsonModel):
    book: str  # USFM code
    chapters: list[TranslationChapter]


# --- Normalised commentary book ({commentator}/{BOOK}.json) ---


class CommentaryText(JsonModel):
    """A commentator's note: paragraphs separated by blank lines, and the Scripture it cites
    as compact references (``MAT 12:9-21``, see ``sources/refs.py``)."""

    text: str
    refs: list[str] = Field(default_factory=list)


class CommentaryItem(CommentaryText):
    """A note on one verse, or on ``verse`` to ``verseEnd`` when the commentator covers a range."""

    verse: Annotated[int, Field(ge=1)]
    verse_end: Annotated[int, Field(ge=1)] | None = None


class CommentaryChapter(JsonModel):
    number: Annotated[int, Field(ge=1)]
    introduction: CommentaryText | None = None  # the commentator's notes on the whole chapter
    items: list[CommentaryItem]


class NormalizedCommentaryBook(JsonModel):
    book: str
    introduction: CommentaryText | None = None
    chapters: list[CommentaryChapter]
