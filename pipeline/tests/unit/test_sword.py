"""Reading CrossWire SWORD commentary modules (research R2a): index, linked notes, OSIS text."""

from typing import Any

import pytest

from thinkbible_pipeline.sources.refs import parse_osis_ref
from thinkbible_pipeline.sources.sword import SwordCommentary, SwordFormatError, osis_to_text
from thinkbible_pipeline.sources.versification import KJV_VERSES

# Real entries from CrossWire's JFB 3.0 and MHC 2.2 (public domain), trimmed.
JFB_MARK_4_3 = (
    '<div type="x-milestone" subType="x-preverse" sID="pv13890"/><div sID="gen26732" '
    'type="x-p"/><div type="x-milestone" subType="x-preverse" eID="pv13890"/><hi type="bold">'
    "3. Hearken; Behold, there went out a sower to sow--</hi>What means this? See on "
    '<reference osisRef="Mark.4.14">Mr 4:14</reference>.<div eID="gen26732" type="x-p"/> '
    '<div sID="gen26733" type="x-p"/> First Case: The Wayside. (<reference osisRef="Mark.4.4">'
    'Mr 4:4</reference>, <reference osisRef="Mark.4.15">15</reference>). '
    '<div eID="gen26733" type="x-p"/>'
)
JFB_MARK_3 = (
    '<title type="x-s2">CHAPTER 3</title><div sID="g1" type="x-p"/>'
    '<reference osisRef="Mark.3.1-Mark.3.12">Mr 3:1-12</reference>. The Healing of a Withered '
    'Hand. ( = <reference osisRef="Matt.12.9-Matt.12.21">Mt 12:9-21</reference>). See on '
    '<reference osisRef="Matt.12.9-Matt.12.21">Mt 12:9-21</reference>.<div eID="g1" type="x-p"/>'
)
MHC_PASSAGE = (
    '<title type="x-s3">The Parable of the Sower.</title> <div sID="g2" type="x-p"/> '
    '<hi type="super">1</hi> And he began again to teach by the sea side &amp; the shore.'
    '<note type="x-footnote">An editor\'s note.</note><div eID="g2" type="x-p"/>'
    '<lg><l level="1">The Lord is my shepherd;</l><l level="2">I shall not want.</l></lg>'
)


def test_kjv_versification_totals() -> None:
    assert len(KJV_VERSES) == 66
    assert sum(len(v) for v in KJV_VERSES.values()) == 1189
    assert sum(sum(v) for v in KJV_VERSES.values()) == 31102
    assert KJV_VERSES["PSA"][118] == 176 and KJV_VERSES["MRK"][3] == 41


def test_osis_to_text_keeps_words_paragraphs_and_references() -> None:
    note = osis_to_text(JFB_MARK_4_3)
    assert note is not None
    assert note.text == (
        "3. Hearken; Behold, there went out a sower to sow--What means this? See on Mr 4:14.\n\n"
        "First Case: The Wayside. (Mr 4:4, 15)."
    )
    assert note.refs == ["MRK 4:14", "MRK 4:4", "MRK 4:15"]


def test_osis_titles_poetry_entities_and_notes() -> None:
    note = osis_to_text(MHC_PASSAGE)
    assert note is not None
    paragraphs = note.text.split("\n\n")
    assert paragraphs[0] == "The Parable of the Sower."
    assert paragraphs[1] == "1 And he began again to teach by the sea side & the shore."
    assert paragraphs[2] == "The Lord is my shepherd;\nI shall not want."
    assert "editor" not in note.text  # publisher's footnotes are dropped


def test_osis_with_no_words_is_none() -> None:
    assert osis_to_text('<div type="x-p" sID="1"/> <chapter osisID="Mark.4"/>') is None
    assert osis_to_text("") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Matt.12.9-Matt.12.21", ["MAT 12:9-21"]),
        ("Matt.12.9-Matt.13.2", ["MAT 12:9-13:2"]),
        ("Gen.5", ["GEN 5"]),
        ("Psa.23.1 Joh.3.16 Mar.4.3", ["PSA 23:1", "JHN 3:16", "MRK 4:3"]),  # Clarke's names
        ("Pr.10.19 11.12 17.27 28", ["PRO 10:19", "PRO 11:12", "PRO 17:27", "PRO 17:28"]),
        ("Lu.24.6 7-44 Mk 16.7", ["LUK 24:6", "LUK 24:7-44", "MRK 16:7"]),
        ("1Macc.2.1 Sir.3.4", []),  # Apocrypha: not in the 66 books
        ("Rom.30", []),  # no such chapter
        ("Num.15.4-Num.7.28", ["NUM 15:4"]),  # a backwards range keeps its start
        ("Bible:John.1.1", ["JHN 1:1"]),
    ],
)
def test_parse_osis_ref(value: str, expected: list[str]) -> None:
    assert parse_osis_ref(value) == expected


def _module(sword_zip: Any, **kw: Any) -> SwordCommentary:
    entries = {
        ("MRK", 0, 0): "<title>THE GOSPEL ACCORDING TO MARK</title>",
        ("MRK", 3, 0): JFB_MARK_3,
        ("MRK", 4, 1): MHC_PASSAGE,
        ("MRK", 4, 3): JFB_MARK_4_3,
        ("MRK", 4, 9): "<hi>9. He that hath ears</hi>",
        ("GEN", 1, 1): "In the beginning",
    }
    links = {("MRK", 4, v): ("MRK", 4, 3) for v in (4, 5, 6)}  # one note on 4:3-6
    return SwordCommentary(sword_zip(entries, links=links, **kw))


@pytest.mark.parametrize("driver", ["zCom", "zCom4"])
def test_book_items_ranges_and_introductions(sword_zip: Any, driver: str) -> None:
    module = _module(sword_zip, driver=driver)
    assert module.conf.name == "TEST" and module.conf.license == "Public Domain"
    mark = module.book("MRK")
    assert mark is not None and mark.book == "MRK"
    assert mark.introduction is not None
    assert mark.introduction.text == "THE GOSPEL ACCORDING TO MARK"
    assert [c.number for c in mark.chapters] == [3, 4]
    three, four = mark.chapters
    assert three.items == [] and three.introduction is not None
    assert three.introduction.refs == ["MRK 3:1-12", "MAT 12:9-21"]  # "See on Mt 12:9-21"
    assert [(i.verse, i.verse_end) for i in four.items] == [(1, None), (3, 6), (9, None)]
    assert four.items[1].refs == ["MRK 4:14", "MRK 4:4", "MRK 4:15"]


def test_book_with_no_notes_is_none(sword_zip: Any) -> None:
    module = _module(sword_zip)
    assert module.book("REV") is None
    genesis = module.book("GEN")
    assert genesis is not None and genesis.chapters[0].items[0].text == "In the beginning"


def test_index_must_match_kjv_versification(sword_zip: Any) -> None:
    with pytest.raises(SwordFormatError, match="KJV scheme needs"):
        SwordCommentary(sword_zip({("MRK", 1, 1): "x"}, drop_entries=1))


@pytest.mark.parametrize(
    "extra",
    ["ModDrv=RawCom\n", "SourceType=ThML\n", "Versification=NRSV\n", "CompressType=LZSS\n"],
)
def test_unsupported_modules_are_refused(sword_zip: Any, extra: str) -> None:
    data = sword_zip({("MRK", 1, 1): "x"}, driver="zCom4")
    # The first value of a key wins, so put the override first in the conf.
    import io
    import zipfile

    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for item in src.namelist():
            body = src.read(item)
            if item.endswith(".conf"):
                head, _, rest = body.decode().partition("\n")
                body = f"{head}\n{extra}{rest}".encode()
            zf.writestr(item, body)
    with pytest.raises(SwordFormatError):
        SwordCommentary(out.getvalue())
