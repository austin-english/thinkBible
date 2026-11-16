"""Pointers to a commentator's note on another passage (T040, research R4)."""

import pytest

from thinkbible_pipeline.commentary.crossrefs import find_pointers, parse_display_ref


def targets(text: str, refs: list[str] | None = None) -> list[tuple[str, str]]:
    return [(p.kind, p.target.compact()) for p in find_pointers(text, refs)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("See on Mat 3:1-3 (note).", [("see", "MAT 3:1-3")]),  # Clarke
        ("See the note on Mat 3:4", [("see", "MAT 3:4")]),
        ("See the notes on Mat 3:2", [("see", "MAT 3:2")]),
        ("See on Mt 7:28-29.", [("see", "MAT 7:28-29")]),  # JFB
        ("See also Mar 12:2 : - And at the season", [("see", "MRK 12:2")]),
        ("which we had before, Mat 8:2-4", [("see", "MAT 8:2-4")]),  # Henry
        ("which we had before, Matt. viii. 2-4. It teaches us", [("see", "MAT 8:2-4")]),
        ("parallel place (Matt. xxiii.); it is here contracted", [("see", "MAT 23")]),
        ("( = Mat 3:1-12; Luke 3:1-18)", [("parallel", "MAT 3:1-12"), ("parallel", "LUK 3:1-18")]),
        ("( = Mt 13:1-23, 31, 32; Lu 8:4-18).",
         [("parallel", "MAT 13:1-23"), ("parallel", "LUK 8:4-18")]),
        # JFB sometimes breaks "( =" across a paragraph; a list item can continue the last book.
        ("Mr 1:21-39. Healing\n\n= Lu 4:31-44; Mt 8:14-17; 4:23-25).",
         [("parallel", "LUK 4:31-44"), ("parallel", "MAT 8:14-17"), ("parallel", "MAT 4:23-25")]),
        ("See on Joh 18:28. See on Mr 4:14.", [("see", "JHN 18:28"), ("see", "MRK 4:14")]),
        ("see on this point, and as in their synagogue", []),
        ("Compare Joh 16:28", []),  # a citation, not a pointer
    ],
)  # fmt: skip
def test_pointer_patterns(text: str, expected: list[tuple[str, str]]) -> None:
    assert targets(text) == expected


def test_tagged_reference_gives_the_exact_range() -> None:
    # Henry names the chapter only; the module's tag on the same reference has the verses.
    text = "parallel place (Matt. xxiii.); it is here contracted."
    assert targets(text, ["LUK 1:32", "MAT 23:1-39"]) == [("see", "MAT 23:1-39")]


def test_duplicates_are_dropped() -> None:
    assert targets("See on Mt 4:13. And again, see on Mt 4:13.") == [("see", "MAT 4:13")]


@pytest.mark.parametrize(
    ("text", "compact"),
    [
        ("Mr 3:13-19. The Twelve", "MRK 3:13-19"),
        ("Mr 1:12, 13. Temptation", "MRK 1:12"),
        ("Matt. viii. 2-4", "MAT 8:2-4"),
        ("Luke 3:1-18", "LUK 3:1-18"),
        ("Joh 18:28-19:16", "JHN 18:28"),
    ],
)
def test_display_references(text: str, compact: str) -> None:
    found = parse_display_ref(text)
    assert found is not None and found[0].compact() == compact


@pytest.mark.parametrize("text", ["Mr 99:1", "Mt 3:99", "The 3:1", "2-3. As it is written"])
def test_not_references(text: str) -> None:
    found = parse_display_ref(text)
    assert found is None or found[0].verse is None
