"""Gather each commentator's notes for one section: what the model is given (research R4).

Commentators file their notes by verse, but a note often carries more than its verse:
- JFB ends a note with the headings of the passages that follow ("Mr 1:12, 13. Temptation of
  Christ. ( = Mt 4:1-11; Lu 4:1-13). See on Mt 4:1-11."), because it has nothing more to say on
  them than where to look.
- Chapter introductions are outlines (Henry) or the same passage headings (JFB).

So every note and introduction is split into **blocks**: a paragraph that opens with a passage of
this chapter ("Mr 3:13-19. …") starts a block for that passage; the text before it belongs to the
note's own verses (or, in an introduction, to the whole chapter). A section's excerpt from each
commentator is then, in this order:

1. **Notes**: every block whose passage overlaps the section. Henry's notes cover whole passages
   ("divisions"), so a division that only partly overlaps comes in whole.
2. **The chapter introduction**: its opening text and the blocks overlapping the section.
3. **Pointers, one hop** (``crossrefs.py``): the commentator's own note on the passage they point
   to, labelled as a parallel passage note. Explicit pointers ("See on Mt 12:9-21") are always
   followed; "( = Mt …; Lu …)" parallel lists only when the commentator says little on the
   section itself. A pointer to a whole chapter brings only that chapter's introduction.

Each excerpt is capped at ``excerpt_cap_tokens`` (tokens estimated as characters / 4). Parts are
kept in the order above, so pointers are the first to go, and the trim is recorded. Only a record
of the excerpt (sha256, tokens, parts) is stored in the draft, never its text (data-model §2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from thinkbible_core.ids import resolve_book
from thinkbible_pipeline.commentary.crossrefs import find_pointers, parse_display_ref
from thinkbible_pipeline.commentary.preface import split_preface
from thinkbible_pipeline.drafts.models import ExcerptRecord, SectionMapEntry
from thinkbible_pipeline.jsonio import sha256_hex
from thinkbible_pipeline.sources.models import CommentaryChapter, NormalizedCommentaryBook
from thinkbible_pipeline.sources.refs import Ref
from thinkbible_pipeline.sources.snapshot import SourceLibrary

# The commentators every pack draws on (content/schema: commentator ids), in prompt order.
COMMENTATORS: tuple[str, ...] = ("matthew-henry", "jamieson-fausset-brown", "adam-clarke")

# Below this many tokens of the commentator's own notes, "( = …)" parallels are followed too.
THIN_TOKENS = 250
# At most this many pointers are followed per commentator per section.
MAX_POINTERS = 4

PartKind = Literal["note", "introduction", "parallel"]


def tokens(text: str) -> int:
    return (len(text) + 3) // 4


@dataclass(frozen=True)
class ExcerptPart:
    kind: PartKind
    key: str  # what it is: "MRK 1:1-8", "MRK 3 intro", "MAT 12:9-21"
    label: str  # the heading the model sees
    text: str
    refs: tuple[str, ...] = ()

    @property
    def rendered(self) -> str:
        return f"[{self.label}]\n{self.text}"


@dataclass
class Excerpt:
    commentator: str
    parts: list[ExcerptPart] = field(default_factory=list)
    cross_refs: list[str] = field(default_factory=list)  # pointer targets followed
    trimmed: bool = False

    @property
    def text(self) -> str:
        return "\n\n".join(p.rendered for p in self.parts)

    @property
    def tokens(self) -> int:
        return tokens(self.text) if self.parts else 0

    def record(self) -> ExcerptRecord:
        return ExcerptRecord(
            sha256=sha256_hex(self.text.encode()),
            tokens=self.tokens,
            items=[p.key for p in self.parts],
            cross_refs=self.cross_refs,
            trimmed=self.trimmed,
        )


@dataclass(frozen=True)
class _Block:
    passage: Ref | None  # None: the whole chapter (an introduction's opening text)
    key: str
    text: str
    refs: tuple[str, ...]


def _name(book: str) -> str:
    return resolve_book(book).name


def _passage_label(ref: Ref) -> str:
    return f"{_name(ref.book)} {ref.compact().split(' ', 1)[1]}"


def _blocks(
    text: str, refs: list[str], book: str, chapter: int, own: Ref | None, own_key: str
) -> list[_Block]:
    """Split a note or introduction at paragraphs that open with a passage of this chapter."""
    groups: list[tuple[Ref | None, str, list[str]]] = [(own, own_key, [])]
    for para in text.split("\n\n"):
        found = parse_display_ref(para)
        head = found[0] if found else None
        if head is not None and head.book == book and head.chapter == chapter:
            groups.append((head, head.compact(), [para]))
        elif not (para.upper().startswith("CHAPTER ") and len(para.split()) <= 3):
            groups[-1][2].append(para)
    return [
        _Block(passage, key, "\n\n".join(paras), tuple(refs))
        for passage, key, paras in groups
        if paras
    ]


def _chapter_blocks(
    book: str, chapter: CommentaryChapter, commentator: str
) -> tuple[list[_Block], list[_Block]]:
    """A chapter's blocks: (introduction's opening text, every passage block).

    The book preface the first note carries (``commentary/preface.py``) is left out: it feeds the
    book introduction, not the first section.
    """
    opening: list[_Block] = []
    passages: list[_Block] = []
    if chapter.introduction is not None:
        intro = chapter.introduction
        for b in _blocks(
            intro.text, intro.refs, book, chapter.number, None, f"{book} {chapter.number} intro"
        ):
            (opening if b.passage is None else passages).append(b)
    for n, item in enumerate(chapter.items):
        own = Ref(book, chapter.number, item.verse, end_verse=item.verse_end)
        text = item.text
        if chapter.number == 1 and n == 0:
            text = split_preface(commentator, text)[1]
        passages += _blocks(text, item.refs, book, chapter.number, own, own.compact())
    return opening, passages


def _overlapping(
    blocks: list[_Block], book: str, chapter: int, start: int, end: int
) -> list[_Block]:
    return [
        b for b in blocks if b.passage is not None and b.passage.overlaps(book, chapter, start, end)
    ]


def _chapter(commentary: NormalizedCommentaryBook | None, number: int) -> CommentaryChapter | None:
    if commentary is None:
        return None
    return next((c for c in commentary.chapters if c.number == number), None)


_PARALLEL = ": the commentator's note on a parallel passage, applying to this section's passage"


def _follow(target: Ref, commentator: str, library: SourceLibrary) -> tuple[str, list[_Block]]:
    """The commentator's own note on ``target``: (what it is, its blocks). A whole chapter, or a
    passage without notes of its own, gives the chapter introduction's opening text."""
    chapter = _chapter(library.commentary(commentator, target.book), target.chapter)
    if chapter is None:
        return "", []
    opening, passages = _chapter_blocks(target.book, chapter, commentator)
    if target.verse is not None:
        (_, first), (last_chapter, last) = target.span()
        end = last if last_chapter == target.chapter else 999
        chosen = _overlapping(passages, target.book, target.chapter, first, end)
        if chosen:
            return _passage_label(target), chosen
    return f"{_name(target.book)} {target.chapter} (introduction)", opening


def gather(
    section: SectionMapEntry,
    book: str,
    commentator: str,
    library: SourceLibrary,
    *,
    cap_tokens: int,
) -> Excerpt:
    """One commentator's excerpt for ``section`` of ``book`` (a USFM code)."""
    excerpt = Excerpt(commentator)
    chapter = _chapter(library.commentary(commentator, book), section.chapter)
    if chapter is None:
        return excerpt
    start, end = section.verse_start, section.verse_end
    opening, passages = _chapter_blocks(book, chapter, commentator)
    intro_keys = {f"{book} {chapter.number} intro"}

    notes = [
        b
        for b in _overlapping(passages, book, section.chapter, start, end)
        if b.key not in intro_keys
    ]
    candidates = [
        ExcerptPart("note", b.key, _passage_label(b.passage), b.text, b.refs)
        for b in notes
        if b.passage is not None
    ]
    own_tokens = sum(tokens(p.text) for p in candidates)
    if opening:
        candidates.append(
            ExcerptPart(
                "introduction",
                f"{book} {section.chapter} intro",
                f"Introduction to {_name(book)} {section.chapter}",
                "\n\n".join(b.text for b in opening),
                tuple(r for b in opening for r in b.refs),
            )
        )

    followed: dict[str, str] = {}  # pointer target → key of the part it brought
    seen_blocks: set[str] = {c.key for c in candidates}
    for part in list(candidates):
        for pointer in find_pointers(part.text, list(part.refs)):
            if len(followed) >= MAX_POINTERS:
                break
            if pointer.kind == "parallel" and own_tokens >= THIN_TOKENS:
                continue
            target = pointer.target.compact()
            if target in followed or pointer.target.overlaps(book, section.chapter, start, end):
                continue
            what, blocks = _follow(pointer.target, commentator, library)
            blocks = [b for b in blocks if b.key not in seen_blocks]
            if not blocks:
                continue
            seen_blocks.update(b.key for b in blocks)
            followed[target] = target
            candidates.append(
                ExcerptPart(
                    "parallel",
                    target,
                    f"Parallel passage note, {what}{_PARALLEL}",
                    "\n\n".join(b.text for b in blocks),
                    tuple(dict.fromkeys(r for b in blocks for r in b.refs)),
                )
            )

    used = 0
    for part in candidates:
        cost = tokens(part.rendered + "\n\n")
        if used + cost > cap_tokens:
            excerpt.trimmed = True
            if not excerpt.parts:  # one part over the cap on its own: keep whole paragraphs
                kept: list[str] = []
                for para in part.text.split("\n\n"):
                    if tokens(part.label + "\n\n".join([*kept, para])) > cap_tokens:
                        break
                    kept.append(para)
                if kept:
                    excerpt.parts.append(
                        ExcerptPart(part.kind, part.key, part.label, "\n\n".join(kept), part.refs)
                    )
            break
        excerpt.parts.append(part)
        used += cost
    included = {p.key for p in excerpt.parts}
    excerpt.cross_refs = [t for t, key in followed.items() if key in included]
    return excerpt


def book_prefaces(book: str, library: SourceLibrary, *, cap_tokens: int) -> dict[str, str]:
    """Each commentator's preface to ``book`` (who wrote it, to whom, when, why), for the book
    introduction; commentators without one are left out. Each is cut to ``cap_tokens``."""
    out: dict[str, str] = {}
    for c in COMMENTATORS:
        chapter = _chapter(library.commentary(c, book), 1)
        if chapter is None or not chapter.items:
            continue
        preface, _rest = split_preface(c, chapter.items[0].text)
        if preface:
            out[c] = _cut_to_tokens(preface, cap_tokens)
    return out


def _cut_to_tokens(text: str, cap: int) -> str:
    if tokens(text) <= cap:
        return text
    kept: list[str] = []
    for para in text.split("\n\n"):
        if tokens("\n\n".join([*kept, para])) > cap:
            break
        kept.append(para)
    return "\n\n".join(kept)


def gather_all(
    section: SectionMapEntry, book: str, library: SourceLibrary, *, cap_tokens: int
) -> dict[str, Excerpt]:
    """Every commentator's excerpt for ``section``, in ``COMMENTATORS`` order."""
    return {c: gather(section, book, c, library, cap_tokens=cap_tokens) for c in COMMENTATORS}
