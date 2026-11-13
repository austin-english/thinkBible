"""Normalising API chapters (T030): keep the text and structure, drop presentation fields."""

import json
from pathlib import Path
from typing import Any

from thinkbible_pipeline.sources.models import (
    BreakItem,
    HeadingItem,
    Line,
    SubtitleItem,
    VerseItem,
)
from thinkbible_pipeline.sources.normalize import (
    normalize_translation_book,
    normalize_translation_chapter,
)

API = Path(__file__).resolve().parents[1] / "fixtures" / "api"


def raw(name: str) -> Any:
    return json.loads((API / f"{name}.json").read_text(encoding="utf-8"))


def verses(chapter: Any) -> dict[int, VerseItem]:
    return {i.number: i for i in chapter.items if isinstance(i, VerseItem)}


def test_bsb_omits_7_16_and_keeps_its_footnote() -> None:
    ch = normalize_translation_chapter(raw("BSB_MRK_7"))
    assert ch.number == 7
    vs = verses(ch)
    assert 16 not in vs and {15, 17} <= set(vs)
    assert vs[15].note_ids == [43]
    note = next(f for f in ch.footnotes if f.note_id == 43)
    assert (note.chapter, note.verse) == (7, 15)
    assert note.text.startswith("BYZ and TR include 16")


def test_kjv_has_7_16() -> None:
    vs = verses(normalize_translation_chapter(raw("eng_kjv_MRK_7")))
    assert {15, 16, 17} <= set(vs)
    # Red-letter markup is presentation: the words stay, the flag goes.
    assert vs[6].text.startswith("He answered and said unto them, Well hath Esaias prophesied")
    assert vs[6].lines is None


def test_poetry_lines_with_indent() -> None:
    vs = verses(normalize_translation_chapter(raw("BSB_MRK_7")))
    six = vs[6]
    assert six.lines is not None
    assert [(line.indent) for line in six.lines] == [0, 1, 2]
    assert six.lines[0].text.endswith("as it is written:")
    assert six.lines[1] == Line(text="\u2018These people honor Me with their lips,", indent=1)
    assert six.text == " ".join(line.text for line in six.lines)
    seven = vs[7]
    assert seven.lines is not None and [line.indent for line in seven.lines] == [1, 2]
    assert seven.note_ids == [38]


def test_headings_and_paragraph_breaks() -> None:
    ch = normalize_translation_chapter(raw("BSB_MRK_7"))
    kinds = [type(i).__name__ for i in ch.items]
    assert "HeadingItem" in kinds
    heading = next(i for i in ch.items if isinstance(i, HeadingItem))
    assert heading.text == "What Defiles a Man"
    breaks = [i for i in ch.items if isinstance(i, BreakItem)]
    assert breaks and all(b.paragraph for b in breaks)
    assert {b.marker for b in breaks} <= {"m", "p"}


def test_psalm_title_is_kept_before_verse_one() -> None:
    ch = normalize_translation_chapter(raw("BSB_PSA_3"))
    kinds = [i.type for i in ch.items]
    assert kinds[:3] == ["heading", "subtitle", "break"]
    title = ch.items[1]
    assert isinstance(title, SubtitleItem)
    assert title.text == "A Psalm of David, when he fled from his son Absalom."
    two = verses(ch)[2]
    assert two.lines is not None and two.lines[-1] == Line(text="Selah", indent=0)
    assert two.note_ids == [5]


def test_presentation_fields_are_dropped() -> None:
    book = normalize_translation_book("MRK", [raw("BSB_MRK_16"), raw("BSB_MRK_7")])
    assert [c.number for c in book.chapters] == [7, 16]  # sorted by chapter
    text = json.dumps(book.to_doc())
    assert "audio" not in text.lower() and "ApiLink" not in text
    sixteen = book.chapters[1]
    note = next(f for f in sixteen.footnotes if f.verse == 8)
    assert note.text.startswith("Some early manuscripts end the Gospel of Mark after verse 8")
