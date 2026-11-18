"""Building a book's study pack and verse files from its drafts (T067, R13, data-model §1)."""

from datetime import UTC, datetime
from typing import Any

import pytest

from thinkbible_core.schema import validate
from thinkbible_pipeline.drafts.models import BookIntro, DroppedItem
from thinkbible_pipeline.jsonio import sha256_hex
from thinkbible_pipeline.publish.build import BuildError, build_pack, next_version

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def build(book: Any, previous: Any = None, live: Any = None) -> Any:
    return build_pack(book.store, book.library, previous=previous, live=live, now=NOW)


def test_the_first_publish_is_1_0_0_and_valid(publish_book: Any) -> None:
    draft = publish_book.draft("2jn-1-1")
    draft.dropped = [DroppedItem(item_id="2jn-1-1-q9", stage="review", reason="graded 2",
                                 item={"text": "A dropped question?"})]  # fmt: skip
    publish_book.write("2jn-1-1", draft)
    built = build(publish_book)
    assert built.version == "1.0.0" and built.change == "first"
    assert sorted(built.files) == ["study.json", "verses/bsb.json", "verses/kjv.json"]
    study = built.study
    assert [s.id for s in study.sections] == ["2jn-1-1", "2jn-1-7"]
    items = [i for s in study.sections for i in [*s.key_ideas, *s.questions]]
    assert {i.added_in for i in items} == {"1.0.0"}
    assert "2jn-1-1-q9" not in built.files["study.json"].decode()  # dropped items stay out
    # Every file validates, and the pack points at the verse files by their sha256.
    assert validate(study.to_doc(), "study-pack") == []
    for tr in ("bsb", "kjv"):
        ref = next(t for t in study.translations if t.id == tr)
        assert ref.sha256 == sha256_hex(built.files[f"verses/{tr}.json"])
    assert study.translations[0].id == "bsb"  # the default translation comes first


def test_provenance_names_every_source_and_the_build(publish_book: Any) -> None:
    study = build(publish_book).study
    assert [s.id for s in study.sources] == ["bsb", "kjv", "matthew-henry"]
    henry = study.sources[2]
    assert henry.kind == "commentary" and henry.short_name == "Henry"
    assert henry.snapshot_sha256 == publish_book.library.manifest.sources[
        "matthew-henry"].books["2JN"].sha256  # fmt: skip
    assert study.build.models == {"generate": "claude-sonnet-5-5", "review": "claude-opus-5-5"}
    assert study.build.prompt_versions["review"] == "_shared/context@v1+review@v11"
    assert study.build.question_guide_version == "v4"


def test_verse_files_carry_paragraphs_poetry_and_omissions(publish_book: Any) -> None:
    built = build(publish_book)
    bsb = built.verses["bsb"]
    verses = {v.number: v for v in bsb.chapters[0].verses}
    assert verses[1].paragraph_start and verses[7].paragraph_start and not verses[2].paragraph_start
    assert [(ln.text, ln.indent) for ln in verses[3].lines or []] == [
        ("Grace, mercy,", 1), ("and peace", 4)  # the source's indent 6 is capped at 4
    ]  # fmt: skip
    assert bsb.omitted_verses == [] and bsb.pack_version == "1.0.0"
    assert validate(bsb.to_doc(), "verses") == []


def test_the_book_introduction_comes_from_the_first_section(publish_book: Any) -> None:
    draft = publish_book.draft("2jn-1-1")
    quote = {"commentator": "matthew-henry", "text": "Henry's words on the letter."}
    draft.book_intro = BookIntro(
        introduction={
            "text": "John writes a short letter to a chosen lady.",
            "sources": ["matthew-henry"],
            "quotes": [quote],
        }
    )
    publish_book.write("2jn-1-1", draft)
    intro = build(publish_book).study.introduction
    assert intro is not None and intro.sources == ["matthew-henry"]


def test_no_change_publishes_nothing_and_changes_bump_the_version(publish_book: Any) -> None:
    first = build(publish_book).study
    assert build(publish_book, previous=first) is None
    # A changed note only: a patch.
    draft = publish_book.draft("2jn-1-7")
    draft.section["context"] = "The elder warns against deceivers."
    publish_book.write("2jn-1-7", draft)
    patch = build(publish_book, previous=first)
    assert patch.version == "1.0.1" and patch.change == "patch"
    # A new item: a minor version. Items already live keep the version they went live with.
    draft.section["keyIdeas"].append({**draft.section["keyIdeas"][0], "id": "2jn-1-7-k2"})
    publish_book.write("2jn-1-7", draft)
    minor = build(publish_book, previous=patch.study, live=first)
    assert minor.version == "1.1.0" and minor.change == "minor"
    added = {i.id: i.added_in for s in minor.study.sections for i in s.key_ideas}
    assert added["2jn-1-7-k1"] == "1.0.0" and added["2jn-1-7-k2"] == "1.1.0"


def test_versions_only_increase() -> None:
    assert next_version(None, "first") == "1.0.0"
    assert next_version("1.4.2", "minor") == "1.5.0"
    assert next_version("1.4.2", "patch") == "1.4.3"


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ("ungenerated", "2jn-1-7: not generated"),
        ("failed", "2jn-1-7: failed (review: no usable question)"),
        ("ungraded", "2jn-1-7: not graded"),
        ("moved", "2jn-1-7: the draft is for 1:8-13, but the section map says 1:7-13"),
    ],
)
def test_an_incomplete_book_is_not_built(publish_book: Any, change: str, problem: str) -> None:
    draft = publish_book.draft("2jn-1-7")
    if change == "ungenerated":
        draft.stages = {}
    elif change == "failed":
        draft.failed = "review: no usable question"
    elif change == "ungraded":
        del draft.stages["review"]
    else:
        draft.section["verseStart"] = 8
    publish_book.write("2jn-1-7", draft)
    with pytest.raises(BuildError) as err:
        build(publish_book)
    assert err.value.problems[0].startswith(problem)


def test_a_pack_breaking_the_contract_is_not_built(publish_book: Any) -> None:
    draft = publish_book.draft("2jn-1-1")
    draft.section["questions"][0]["targets"] = ["2jn-1-1-k7"]  # no such key idea
    publish_book.write("2jn-1-1", draft)
    with pytest.raises(BuildError) as err:
        build(publish_book)
    assert any("2jn-1-1-q1" in p for p in err.value.problems)
