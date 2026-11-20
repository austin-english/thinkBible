"""Each commentator's introduction to a book, which their first note carries (2026-11-18).

The SWORD modules put a commentator's preface to a book (who wrote it, to whom, when, why) at the
start of their note on its first verses, not in a separate introduction. Left there, it reached only
the first section's prompt (some 20,000 characters for Mark 1:1-11), and every other section's
context note had nothing to draw on. ``split_preface`` separates it, by rules that hold across the
snapshot's books:

- Jamieson-Fausset-Brown: the preface ends at its ``CHAPTER 1`` (``PSALM 1``) heading, or, in a
  one-chapter book, at its first verse note (``1.``).
- Adam Clarke: the preface ends before the chapter summary that precedes ``Verse 1``.
- Matthew Henry: the note runs preface, chapter summary, section heading, then the verse text
  (``1 Paul, an apostle…``); the preface is everything before the chapter summary.

Many books have no preface (JFB often gives only a title): then nothing is split.

The preface feeds the book introduction (``stages/intro.py``); the rest stays the first note. The
frozen snapshot is unchanged: the split happens when the pipeline reads it.
"""

from __future__ import annotations

import re

_JFB_FIRST_CHAPTER = re.compile(r"\n\n(?:CHAPTER|PSALM) 1\n")
_JFB_FIRST_VERSE = re.compile(r"\n\n1\. ")
_CLARKE_FIRST_VERSE = re.compile(r"\n\nVerse 1\n")
_CHAPTER_SUMMARY = re.compile(r"\b[1-3]?[A-Z][a-z]{1,3}\.? \d+:\d+")  # "Mar 1:40-45"
_HENRY_FIRST_VERSE = re.compile(r"^1 \S")

MIN_PREFACE_CHARS = 200  # anything shorter is a title, not a preface


def split_preface(commentator: str, text: str) -> tuple[str | None, str]:
    """(the book preface, or None; the rest of the note) for a commentator's first note."""
    cut: int | None = None
    if commentator == "jamieson-fausset-brown":
        m = _JFB_FIRST_CHAPTER.search(text) or _JFB_FIRST_VERSE.search(text)
        cut = m.start() if m else None
    elif commentator == "adam-clarke":
        m = _CLARKE_FIRST_VERSE.search(text)
        if m:
            head = text[: m.start()]
            paragraphs = head.split("\n\n")
            # The paragraph just before "Verse 1" is usually the chapter summary: it stays.
            if len(paragraphs) > 1 and _CHAPTER_SUMMARY.search(paragraphs[-1]):
                cut = len("\n\n".join(paragraphs[:-1]))
            else:
                cut = m.start()
    elif commentator == "matthew-henry":
        paragraphs = text.split("\n\n")
        first_verse = next(
            (i for i, para in enumerate(paragraphs) if _HENRY_FIRST_VERSE.match(para)), None
        )
        # preface…, chapter summary, section heading, "1 …": at least one preface paragraph
        if first_verse is not None and first_verse >= 3:
            cut = len("\n\n".join(paragraphs[: first_verse - 2]))
    if cut is None:
        return None, text
    preface, rest = text[:cut].strip(), text[cut:].strip()
    if len(preface) < MIN_PREFACE_CHARS or not rest:
        return None, text
    return preface, rest
