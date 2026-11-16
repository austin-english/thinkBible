"""Building sections (T039, research R5): headings, chapter bounds, merging, splitting, coverage."""

from itertools import pairwise
from typing import Any

from thinkbible_pipeline.drafts.models import SectionMapEntry
from thinkbible_pipeline.sections.builder import build_sections
from thinkbible_pipeline.sources.models import NormalizedCommentaryBook, NormalizedTranslationBook
from thinkbible_pipeline.sources.versification import KJV_VERSES


def bsb(chapters: dict[int, dict[str, Any]]) -> NormalizedTranslationBook:
    """A BSB Mark: per chapter, ``headings`` {verse: title}, ``paragraphs`` and ``omit`` verses."""
    out = []
    for number, spec in chapters.items():
        items: list[dict[str, Any]] = []
        for v in range(1, KJV_VERSES["MRK"][number - 1] + 1):
            if v in spec.get("omit", ()):
                continue
            if v in spec.get("headings", {}):
                items.append({"type": "heading", "text": spec["headings"][v]})
            if v in spec.get("paragraphs", ()):
                items.append({"type": "break", "paragraph": True, "marker": "p"})
            items.append({"type": "verse", "number": v, "text": f"Verse {v}."})
        out.append({"number": number, "items": items})
    return NormalizedTranslationBook.model_validate({"book": "MRK", "chapters": out})


def henry(divisions: dict[int, list[tuple[int, int]]]) -> NormalizedCommentaryBook:
    return NormalizedCommentaryBook.model_validate(
        {
            "book": "MRK",
            "chapters": [
                {"number": c, "items": [{"verse": a, "verseEnd": b, "text": "…"} for a, b in ds]}
                for c, ds in divisions.items()
            ],
        }
    )


def chapter(sections: list[SectionMapEntry], number: int) -> list[tuple[int, int, str, str]]:
    return [
        (s.verse_start, s.verse_end, s.title, s.title_source)
        for s in sections
        if s.chapter == number
    ]


def test_headings_start_sections_and_ids() -> None:
    book = bsb({1: {"headings": {1: "John", 12: "Temptation", 16: "Disciples", 21: "Synagogue",
                                 29: "Peter's House", 35: "Prayer", 40: "Leper"}}})  # fmt: skip
    sections = build_sections("MRK", book, henry({1: [(1, 8), (9, 13), (14, 22)]}))
    assert chapter(sections, 1) == [
        (1, 11, "John", "bsb-heading"),
        (12, 15, "Temptation", "bsb-heading"),
        (16, 20, "Disciples", "bsb-heading"),
        (21, 28, "Synagogue", "bsb-heading"),
        (29, 34, "Peter's House", "bsb-heading"),
        (35, 39, "Prayer", "bsb-heading"),
        (40, 45, "Leper", "bsb-heading"),
    ]
    first = sections[0]
    assert first.id == "mrk-1-1" and sections[1].id == "mrk-1-12"
    assert first.henry_divisions == [1, 9]


def test_sections_never_cross_chapters() -> None:
    book = bsb({1: {"headings": {1: "John", 40: "Leper"}}, 2: {"headings": {5: "Paralytic"}}})
    sections = build_sections("MRK", book, None)
    # Chapter 2 opens mid-passage: a piece of the last heading, flagged for a better title.
    assert chapter(sections, 2)[0] == (1, 4, "Leper (cont.)", "split")
    assert chapter(sections, 2)[1][::2] == (5, "Paralytic")
    assert all(s.verse_end <= KJV_VERSES["MRK"][s.chapter - 1] for s in sections)


def test_short_sections_merge_into_the_next_or_the_previous() -> None:
    book = bsb({1: {"headings": {1: "Patches", 3: "Sabbath", 44: "Ending"}}})
    one = chapter(build_sections("MRK", book, None), 1)
    # 1-2 merges into 3-43 under the longer piece's title; 44-45, the last in the chapter, merges
    # into the previous one. The resulting 1-45 is then split (no paragraph breaks: at the middle).
    titles = [title for *_r, title, _s in one]
    assert one[0] == (1, 11, "Sabbath", "bsb-heading")
    assert one[-1][1] == 45
    assert "Patches" not in titles and "Ending" not in titles
    assert titles[1:] == ["Sabbath (cont.)"] * (len(one) - 1)


def test_long_sections_split_at_henry_then_paragraph_then_middle() -> None:
    book = bsb(
        {
            1: {"headings": {1: "Henry split", 21: "Paragraph split", 36: "Middle split"},
                "paragraphs": [27]},
        }
    )  # fmt: skip
    sections = build_sections("MRK", book, henry({1: [(1, 8), (9, 20)]}))
    one = chapter(sections, 1)
    # 1-20 splits at Henry's division at 9 (nearest the middle that leaves 3+ verses each side).
    assert one[0] == (1, 8, "Henry split", "bsb-heading")
    assert one[1] == (9, 20, "Henry split (cont.)", "split")
    # 21-35 has no Henry division inside: it splits at the paragraph break at 27.
    assert one[2] == (21, 26, "Paragraph split", "bsb-heading")
    assert one[3] == (27, 35, "Paragraph split (cont.)", "split")
    # 36-45 is 10 verses: no split.
    assert one[4] == (36, 45, "Middle split", "bsb-heading")
    no_breaks = chapter(build_sections("MRK", bsb({1: {"headings": {1: "Long"}}}), None), 1)
    assert all(3 <= end - start + 1 <= 12 for start, end, _t, _s in no_breaks)
    assert [t for *_r, t, _s in no_breaks][1:] == ["Long (cont.)"] * (len(no_breaks) - 1)


def test_every_verse_is_covered_including_kjv_only_verses() -> None:
    book = bsb({7: {"headings": {1: "Tradition", 14: "What Defiles", 24: "Faith"}, "omit": [16]}})
    sections = build_sections("MRK", book, None)
    seven = chapter(sections, 7)
    covered = [v for start, end, *_ in seven for v in range(start, end + 1)]
    assert covered == list(range(1, KJV_VERSES["MRK"][6] + 1))
    assert 16 in covered  # BSB omits 7:16; the KJV has it
    for c, last in enumerate(KJV_VERSES["MRK"], 1):
        ranges = [(s.verse_start, s.verse_end) for s in sections if s.chapter == c]
        assert ranges[0][0] == 1 and ranges[-1][1] == last
        assert all(b[0] == a[1] + 1 for a, b in pairwise(ranges))
