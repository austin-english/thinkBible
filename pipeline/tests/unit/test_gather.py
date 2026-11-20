"""Gathering each commentator's excerpt for a section (T041, research R4)."""

from typing import Any

from thinkbible_pipeline.commentary.gather import (
    THIN_TOKENS,
    focus_on_section,
    gather,
    gather_all,
    without_scripture_copy,
)
from thinkbible_pipeline.drafts.models import SectionMapEntry


def section(chapter: int, start: int, end: int) -> SectionMapEntry:
    return SectionMapEntry(
        id=f"mrk-{chapter}-{start}",
        chapter=chapter,
        verse_start=start,
        verse_end=end,
        title="T",
        title_source="bsb-heading",
    )


def book(code: str, chapters: list[dict[str, Any]]) -> dict[str, Any]:
    return {"book": code, "chapters": chapters}


HENRY = book(
    "MRK",
    [
        {
            "number": 1,
            "introduction": {"text": "In this chapter we have I. John's preaching, ver. 1-8."},
            "items": [
                {"verse": 1, "verseEnd": 8, "text": "Henry on the Baptist."},
                {"verse": 9, "verseEnd": 13, "text": "Henry on the baptism and temptation."},
                {"verse": 14, "verseEnd": 22, "text": "Henry on the first disciples."},
            ],
        }
    ],
)
# JFB files the headings of 1:9-20 at the end of its note on 1:2-3, each with a pointer.
JFB = book(
    "MRK",
    [
        {
            "number": 1,
            "items": [
                {"verse": 2, "verseEnd": 3, "text": (
                    "2-3. As it is written in the prophets.\n\n"
                    "Mr 1:12, 13. Temptation of Christ. ( = Mt 4:1-11; Lu 4:1-13).\n\n"
                    "See on Mt 4:1-11."
                ), "refs": ["MAT 4:1-11", "LUK 4:1-13"]},
                {"verse": 21, "text": "21. And they went into Capernaum--(See on Mt 4:13)."},
            ],
        },
        {
            "number": 3,
            "introduction": {"text": (
                "CHAPTER 3\n\n"
                "Mr 3:1-12. The Healing of a Withered Hand. ( = Mt 12:9-21).\n\n"
                "See on Mt 12:9-21.\n\n"
                "Mr 3:13-19. The Twelve Apostles Chosen.\n\n"
                "See on Lu 6:12-19."
            ), "refs": ["MAT 12:9-21", "LUK 6:12-19"]},
            "items": [],
        },
    ],
)  # fmt: skip
JFB_MATTHEW = book(
    "MAT",
    [
        {
            "number": 4,
            "items": [
                {"verse": 1, "text": "1. Then was Jesus led up of the Spirit."},
                {"verse": 2, "text": "2. And when he had fasted forty days."},
                {"verse": 13, "text": "13. And leaving Nazareth."},
            ],
        },
        {"number": 12, "items": [{"verse": 10, "text": "10. a man which had his hand withered."}]},
    ],
)
CLARKE = book(
    "MRK",
    [{"number": 1, "items": [{"verse": 4, "text": "Verse 4. See on Mat 3:1-3 (note)."}]}],
)
CLARKE_MATTHEW = book(
    "MAT", [{"number": 3, "items": [{"verse": 1, "verseEnd": 3, "text": "Clarke on Matt 3."}]}]
)


def library(make_library: Any) -> Any:
    return make_library(
        {
            ("matthew-henry", "MRK"): HENRY,
            ("jamieson-fausset-brown", "MRK"): JFB,
            ("jamieson-fausset-brown", "MAT"): JFB_MATTHEW,
            ("adam-clarke", "MRK"): CLARKE,
            ("adam-clarke", "MAT"): CLARKE_MATTHEW,
        }
    )


def test_notes_overlapping_the_section_and_whole_henry_divisions(make_library: Any) -> None:
    lib = library(make_library)
    ex = gather(section(1, 1, 11), "MRK", "matthew-henry", lib, cap_tokens=8000)
    assert [p.key for p in ex.parts] == ["MRK 1:1-8", "MRK 1:9-13", "MRK 1 intro"]
    assert ex.parts[1].text == "Henry on the baptism and temptation."  # 9-13: whole division
    # A note inside the section has a plain label; one running past it says so.
    assert ex.parts[0].label == "Mark 1:1-8"
    assert ex.parts[1].label == (
        "Mark 1:9-13; this note runs past the section, which is 1:1-11: what it says about "
        "other verses is context only"
    )
    assert ex.parts[2].label == "Introduction to Mark 1"
    record = ex.record()
    assert record.tokens == ex.tokens and record.items == ["MRK 1:1-8", "MRK 1:9-13", "MRK 1 intro"]
    assert len(record.sha256) == 64 and not record.trimmed


def test_headings_filed_in_another_note_reach_their_section(make_library: Any) -> None:
    lib = library(make_library)
    ex = gather(section(1, 12, 15), "MRK", "jamieson-fausset-brown", lib, cap_tokens=8000)
    keys = [p.key for p in ex.parts]
    assert keys[0] == "MRK 1:12"  # the heading block from the note on 1:2-3, not the whole note
    assert "As it is written" not in ex.parts[0].text
    # Its pointer is followed one hop, to JFB's own notes on Matthew 4:1-11, merged in one part.
    parallel = ex.parts[1]
    assert parallel.kind == "parallel" and parallel.key == "MAT 4:1-11"
    assert parallel.label.startswith("Parallel passage note, Matthew 4:1-11")
    assert "led up of the Spirit" in parallel.text and "fasted forty days" in parallel.text
    assert "leaving Nazareth" not in parallel.text  # 4:13 is outside the target
    assert ex.cross_refs == ["MAT 4:1-11"]
    # The section of the note itself (1:1-11) doesn't get the 1:12 heading block.
    first = gather(section(1, 1, 11), "MRK", "jamieson-fausset-brown", lib, cap_tokens=8000)
    assert [p.key for p in first.parts if p.kind == "note"] == ["MRK 1:2-3"]
    assert "Temptation" not in first.parts[0].text


def test_introduction_blocks_apply_only_to_their_passage(make_library: Any) -> None:
    lib = library(make_library)
    healing = gather(section(3, 1, 6), "MRK", "jamieson-fausset-brown", lib, cap_tokens=8000)
    assert [p.key for p in healing.parts] == ["MRK 3:1-12", "MAT 12:9-21"]
    assert "Twelve Apostles" not in healing.parts[0].text
    assert "withered" in healing.parts[1].text
    twelve = gather(section(3, 13, 19), "MRK", "jamieson-fausset-brown", lib, cap_tokens=8000)
    assert [p.key for p in twelve.parts] == ["MRK 3:13-19"]  # no Luke in this snapshot
    assert twelve.cross_refs == []


def test_explicit_pointers_are_always_followed(make_library: Any) -> None:
    lib = library(make_library)
    ex = gather(section(1, 4, 8), "MRK", "adam-clarke", lib, cap_tokens=8000)
    assert [p.key for p in ex.parts] == ["MRK 1:4", "MAT 3:1-3"]
    assert ex.cross_refs == ["MAT 3:1-3"]


def test_parallel_lists_are_followed_only_when_the_notes_are_thin(make_library: Any) -> None:
    long_note = "word " * (THIN_TOKENS * 4)
    jfb = book(
        "MRK",
        [
            {
                "number": 1,
                "items": [{"verse": 12, "text": f"Mr 1:12, 13. ( = Mt 4:1-11). {long_note}"}],
            }
        ],
    )
    lib = make_library(
        {("jamieson-fausset-brown", "MRK"): jfb, ("jamieson-fausset-brown", "MAT"): JFB_MATTHEW}
    )
    ex = gather(section(1, 12, 15), "MRK", "jamieson-fausset-brown", lib, cap_tokens=8000)
    assert [p.kind for p in ex.parts] == ["note"]


def test_excerpt_is_trimmed_at_a_part_boundary(make_library: Any) -> None:
    lib = library(make_library)
    full = gather(section(1, 1, 11), "MRK", "matthew-henry", lib, cap_tokens=8000)
    cap = full.tokens - 5  # room for everything but the last part
    ex = gather(section(1, 1, 11), "MRK", "matthew-henry", lib, cap_tokens=cap)
    assert ex.trimmed and [p.key for p in ex.parts] == ["MRK 1:1-8", "MRK 1:9-13"]
    assert ex.tokens <= cap and ex.record().trimmed


def test_a_commentator_without_notes_gives_an_empty_excerpt(make_library: Any) -> None:
    lib = library(make_library)
    excerpts = gather_all(section(5, 1, 5), "MRK", lib, cap_tokens=8000)
    assert list(excerpts) == ["matthew-henry", "jamieson-fausset-brown", "adam-clarke"]
    assert all(e.tokens == 0 and e.parts == [] for e in excerpts.values())


def test_henrys_copy_of_the_verses_is_left_out() -> None:
    title, remark = "Exhortations. (b. c. 1451.)", "This discourse is entire (v. 1)."
    note = f"{title}\n\n1 Now therefore hearken, O Israel…\n\n2 Ye shall not add…\n\n{remark}"
    assert without_scripture_copy(note, 1, 40) == f"{title}\n\n{remark}"
    # A number outside the note's verses is not its copy of them ("2 Kings…" in a note on 5-9).
    other = "Title.\n\n2 Kings tells the rest of the story."
    assert without_scripture_copy(other, 5, 9) == other


def test_a_note_over_the_cap_keeps_its_parts_about_the_section(make_library: Any) -> None:
    """Henry on Deuteronomy 4:1-40: the later sections' own verses had been cut off."""
    paras = [
        "General remarks on the chapter.",
        "(1.) On hearing the law, v. 1, 2. " + "x " * 400,
        "(2.) On idolatry, v. 15-18. " + "y " * 400,
        "(3.) On apostasy, v. 25-31. Its end.",
    ]
    assert focus_on_section("\n\n".join(paras), 23, 31) == "\n\n".join([paras[0], paras[3]])
    henry_ch = {
        "number": 4,
        "items": [
            {
                "verse": 1,
                "verseEnd": 40,
                "text": "1 Now therefore hearken…\n\n" + "\n\n".join(paras),
            }
        ],
    }
    lib = make_library({("matthew-henry", "DEU"): book("DEU", [henry_ch])})  # fmt: skip
    sec = SectionMapEntry(id="deu-4-23", chapter=4, verse_start=23, verse_end=31, title="T",
                          title_source="bsb-heading")  # fmt: skip
    roomy = gather(sec, "DEU", "matthew-henry", lib, cap_tokens=8000)
    assert "Now therefore hearken" not in roomy.text and "On idolatry" in roomy.text  # fits whole
    tight = gather(sec, "DEU", "matthew-henry", lib, cap_tokens=200)
    assert "On apostasy, v. 25-31. Its end." in tight.text and "On idolatry" not in tight.text
    assert tight.parts[0].label.endswith("shortened to its parts about this section, to fit")
