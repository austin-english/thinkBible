"""What the ``align`` stage checks in code, with no model calls (T076, R3, R12).

**Wording that leans on the BSB** (R12, revised 2026-11-19): questions are written in plain modern
English for readers of either translation, so an everyday word that differs ("crowd", where the
KJV says "multitude") needs nothing. Two things can leave a KJV reader looking for words their
text doesn't have, and only questions with one of them go to the model for a KJV variant:
1. a quoted phrase ('I am willing') whose words are in the BSB's verses and not in the KJV's
   ('I will');
2. a name the KJV spells differently: one the BSB's book uses and the KJV's never does (Elijah,
   where the KJV's New Testament has Elias).

(Comparing every content word flagged 227 of Mark's 296 questions, nearly all on everyday words.)

**Manuscript notes** (R3), for verses one translation has and the other doesn't:
1. whole verses present in one translation only (Mark 7:16, 9:44, 9:46, 11:26, 15:28 are in the
   KJV, not the BSB), from a diff of the two texts;
2. a passage the BSB's footnotes say early manuscripts end before or leave out ("Some early
   manuscripts end the Gospel of Mark after verse 8", Mark 16:9-20).

Wording-level footnotes ("BYZ and TR in the prophets") are left alone: the brief scopes notes to
verses present in one translation and missing in the other. The notes are written here from fixed
wording, not by a model: they state a fact, so they stay neutral and can't add anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from thinkbible_pipeline.sources.models import NormalizedTranslationBook

_WORD = re.compile(r"[a-z]+")
STOPWORDS = frozenset(
    """a about above after again against all also am an and any are as at be because been before
    being below between both but by can could did do does doing down during each even ever every
    few for from further had has have having he her here hers herself him himself his how i if in
    into is it its itself just let like may me might more most much must my myself no nor not now
    of off on once only or other our ours ourselves out over own same say says said she should so
    some still such than that the their theirs them themselves then there these they this those
    through to too under until up upon us very was we were what when where which while who whom
    whose why will with would yet you your yours yourself yourselves unto thee thou thy thine ye
    hath doth shall shalt art wilt""".split()  # noqa: SIM905
)


def stem(word: str) -> str:
    """A light stem, enough to match "sandals" with "sandal" and "healed" with "heal"."""
    for suffix, keep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3 and not word.endswith("ss"):
            return word[: -len(suffix)] + keep
    return word


def fold(text: str) -> str:
    """Lower case, with the KJV's joined letters spelt out (Bartimæus, Arimathæa)."""
    return text.lower().replace("æ", "ae").replace("œ", "oe")


def content_words(text: str) -> set[str]:
    return {stem(w) for w in _WORD.findall(fold(text).replace("'", "")) if w not in STOPWORDS}


def verse_text(book: NormalizedTranslationBook, chapter: int, start: int, end: int) -> str:
    """The text of verses ``start``-``end`` of ``chapter`` in one translation."""
    out = []
    for ch in book.chapters:
        if ch.number == chapter:
            out += [v.text for v in ch.verses() if start <= v.number <= end]
    return " ".join(out)


_QUOTED = re.compile(r"(?:^|[\s(])'([^']+?)'(?=[\s.,;:?!)]|$)")
_NAME = re.compile(r"(?<![.?!]\s)(?<!^)\b([A-Z][a-z]{2,})\b")


def quoted_phrases(question: str) -> list[str]:
    return [m.group(1) for m in _QUOTED.finditer(question)]


def names(text: str) -> set[str]:
    """Capitalised words, other than a sentence's first word."""
    return {m.group(1) for m in _NAME.finditer(text)}


def bsb_only_words(
    question: str,
    bsb_verses: str,
    kjv_verses: str,
    bsb_book: str = "",
    kjv_book: str = "",
) -> list[str]:
    """What a KJV reader wouldn't find in their text, sorted: the content words of a quoted phrase
    that the BSB's verses use and the KJV's don't, and names the BSB's book uses and the KJV's book
    never does (``bsb_book``, ``kjv_book``: each translation's whole book)."""
    flagged: set[str] = set()
    bsb_words, kjv_words = content_words(bsb_verses), content_words(kjv_verses)
    for phrase in quoted_phrases(question):
        flagged |= content_words(phrase) & bsb_words - kjv_words
    if bsb_book and kjv_book:
        bsb_names, kjv_names = names(bsb_book), set(_WORD.findall(fold(kjv_book)))
        flagged |= {
            n.lower() for n in names(question) if n in bsb_names and fold(n) not in kjv_names
        }
    return sorted(flagged)


def book_text(book: NormalizedTranslationBook) -> str:
    return " ".join(v.text for ch in book.chapters for v in ch.verses())


@dataclass(frozen=True)
class ManuscriptCandidate:
    chapter: int
    verse_start: int
    verse_end: int
    text: str  # the note readers see, at most 280 characters (section.schema.json)


def _verses(book: NormalizedTranslationBook, chapter: int) -> set[int]:
    return {v.number for ch in book.chapters if ch.number == chapter for v in ch.verses()}


def _last_verse(book: NormalizedTranslationBook, chapter: int) -> int:
    return max(_verses(book, chapter), default=0)


_ENDS_AFTER = re.compile(r"manuscripts end [^.]*? after verse (\d+)", re.IGNORECASE)
_LEAVE_OUT = re.compile(
    r"manuscripts do not include [^.]*?(\d+):(\d+)\s*[-\u2013]\s*(?:(\d+):)?(\d+)", re.IGNORECASE
)


def manuscript_candidates(
    bsb: NormalizedTranslationBook,
    kjv: NormalizedTranslationBook,
    book_name: str,
    chapter: int,
    start: int,
    end: int,
) -> list[ManuscriptCandidate]:
    """The manuscript notes for verses ``start``-``end`` of ``chapter``, in verse order."""
    out: list[ManuscriptCandidate] = []
    in_bsb, in_kjv = _verses(bsb, chapter), _verses(kjv, chapter)
    for v in range(start, end + 1):
        if v in in_kjv and v not in in_bsb:
            out.append(ManuscriptCandidate(chapter, v, v, (
                f"Verse {v} is in the KJV but not in the BSB. The BSB follows the earliest "
                "manuscripts, which don't include it; the KJV follows later manuscripts that do."
            )))  # fmt: skip
        elif v in in_bsb and v not in in_kjv:
            out.append(ManuscriptCandidate(chapter, v, v, (
                f"Verse {v} is in the BSB but not in the KJV, which follows manuscripts that "
                "don't include it."
            )))  # fmt: skip
    for ch in bsb.chapters:
        for note in ch.footnotes:
            ended = _ENDS_AFTER.search(note.text)
            if ended and note.chapter == chapter:
                first = int(ended.group(1)) + 1
                last = _last_verse(bsb, chapter)
                if start <= first <= end and first <= last:
                    out.append(ManuscriptCandidate(chapter, first, last, (
                        f"Some early manuscripts end {book_name} after verse {first - 1}. Verses "
                        f"{first}-{last} are in both the BSB and the KJV, which follow manuscripts "
                        "that include them."
                    )))  # fmt: skip
            left_out = _LEAVE_OUT.search(note.text)
            if left_out and int(left_out.group(1)) == chapter:
                first = int(left_out.group(2))
                end_chapter = int(left_out.group(3) or left_out.group(1))
                last = (
                    int(left_out.group(4)) if end_chapter == chapter else _last_verse(bsb, chapter)
                )
                if start <= first <= end:
                    out.append(ManuscriptCandidate(chapter, first, last, (
                        f"The earliest manuscripts don't include this passage ({chapter}:{first}"
                        f" onward). Both the BSB and the KJV print it, following later manuscripts."
                    )))  # fmt: skip
    return sorted(out, key=lambda c: (c.verse_start, c.verse_end))
