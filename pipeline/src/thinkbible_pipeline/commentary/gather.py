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
   ("divisions"), so a division that only partly overlaps comes in whole, labelled as running past
   the section (2026-11-18: Mark 2:18-20's central idea had come from the note's 2:21-22).
2. **The chapter introduction**: its opening text and the blocks overlapping the section.
3. **Pointers, one hop** (``crossrefs.py``): the commentator's own note on the passage they point
   to, labelled as a parallel passage note. Explicit pointers ("See on Mt 12:9-21") are always
   followed; "( = Mt …; Lu …)" parallel lists only when the commentator says little on the
   section itself. A pointer to a whole chapter brings only that chapter's introduction.

Henry opens nearly every note with his own copy of its verses' text (11% of his words). The model
is given the passage separately, so that copy is left out (2026-11-18).

Each excerpt is capped at ``excerpt_cap_tokens`` (tokens estimated as characters / 4). Over the
cap, a note that runs past the section first sheds the paragraphs that discuss only other verses
(by the commentator's own markers, "v. 25", "ver. 3-5"); then parts are kept in the order above,
so pointers are the first to go, the first part that doesn't fit keeps the whole paragraphs that
do, and the trim is recorded. (2026-11-18: a whole-chapter note such
as Henry on Deuteronomy 4:1-40 had been cut before reaching the later sections' own verses.) Only
a record of the excerpt (sha256, tokens, parts) is stored in the draft, never its text
(data-model §2).
"""

from __future__ import annotations

import re
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

# Henry's copy of a note's verses: "1 Now therefore hearken…", one block near the start.
_SCRIPTURE_COPY = re.compile(r"^(\d+) \S")
_SCRIPTURE_COPY_WITHIN = 7  # paragraphs from the start of the note
# A commentator's marker for the verse a paragraph discusses: "v. 25", "ver. 3-5", "vs. 9".
_VERSE_MARK = re.compile(r"\b(?:v|ver|vs)\.\s*(\d+)(?:\s*-\s*(\d+))?")


def without_scripture_copy(text: str, start: int, end: int) -> str:
    """Henry's note without his copy of verses ``start``-``end`` (the model has the passage)."""
    paras = text.split("\n\n")

    def is_copy(p: str) -> bool:
        m = _SCRIPTURE_COPY.match(p)
        return m is not None and start <= int(m.group(1)) <= end

    first = next((i for i, p in enumerate(paras[:_SCRIPTURE_COPY_WITHIN]) if is_copy(p)), None)
    if first is None:
        return text
    last = first
    while last + 1 < len(paras) and is_copy(paras[last + 1]):
        last += 1
    return "\n\n".join(paras[:first] + paras[last + 1 :])


def _marked_verses(paragraph: str) -> set[int]:
    out: set[int] = set()
    for a, b in _VERSE_MARK.findall(paragraph):
        first, last = int(a), int(b) if b else int(a)
        if first <= last < first + 60:
            out.update(range(first, last + 1))
    return out


def focus_on_section(text: str, start: int, end: int) -> str:
    """The paragraphs of a note that discuss this section's verses or no verse in particular."""
    own = set(range(start, end + 1))
    kept = [p for p in text.split("\n\n") if not (v := _marked_verses(p)) or v & own]
    return "\n\n".join(kept)


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


def _note_label(passage: Ref, chapter: int, start: int, end: int) -> str:
    """A note's label; one that runs past the section says so, and what the section is."""
    label = _passage_label(passage)
    first, last = passage.span()
    if first < (chapter, start) or last > (chapter, end):
        label += (
            f"; this note runs past the section, which is {chapter}:{start}-{end}: what it says "
            "about other verses is context only"
        )
    return label


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
        if commentator == "matthew-henry":
            text = without_scripture_copy(text, item.verse, item.verse_end or item.verse)
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


_FOCUSED = "; shortened to its parts about this section, to fit"


def _focused(part: ExcerptPart, section: SectionMapEntry) -> ExcerptPart:
    """A note running past the section, without its paragraphs about other verses only."""
    if part.kind != "note" or "runs past the section" not in part.label:
        return part
    text = focus_on_section(part.text, section.verse_start, section.verse_end)
    if text == part.text or not text.strip():
        return part
    return ExcerptPart(part.kind, part.key, part.label + _FOCUSED, text, part.refs)


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
        ExcerptPart(
            "note", b.key, _note_label(b.passage, section.chapter, start, end), b.text, b.refs
        )
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

    if sum(tokens(p.rendered + "\n\n") for p in candidates) > cap_tokens:
        candidates = [_focused(p, section) for p in candidates]
    used = 0
    for part in candidates:
        cost = tokens(part.rendered + "\n\n")
        if used + cost > cap_tokens:
            excerpt.trimmed = True
            # The part that doesn't fit keeps the whole paragraphs that do (a long parallel note,
            # such as Henry's Matthew 23 for Mark 12:38-40, opens with what the section needs).
            room = cap_tokens - used
            kept: list[str] = []
            for para in part.text.split("\n\n"):
                if tokens(f"[{part.label}]\n" + "\n\n".join([*kept, para]) + "\n\n") > room:
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
