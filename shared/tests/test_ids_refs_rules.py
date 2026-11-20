from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest

from thinkbible_core.ids import (
    BOOKS,
    UnknownBookError,
    key_idea_id,
    parse_item_id,
    parse_section_id,
    question_id,
    resolve_book,
    section_id,
)
from thinkbible_core.models import StudyPack, VerseText
from thinkbible_core.refs import Ref, find_refs, malformed, unresolved
from thinkbible_core.rules import Violation, cross_field_violations
from thinkbible_core.schema import schema_dir

# --- ids ----------------------------------------------------------------------------------------


def test_book_table_is_complete_and_unique() -> None:
    assert len(BOOKS) == 66
    assert len({b.code for b in BOOKS}) == 66
    assert [b.order for b in BOOKS] == list(range(1, 67))


@pytest.mark.parametrize(
    ("given", "code"),
    [("mark", "MRK"), ("Mark", "MRK"), ("MRK", "MRK"), ("mrk", "MRK"), ("1 samuel", "1SA"),
     ("1SA", "1SA"), ("Song of Solomon", "SNG"), ("psalm", "PSA"), ("John", "JHN")],
)  # fmt: skip
def test_resolve_book(given: str, code: str) -> None:
    assert resolve_book(given).code == code


def test_resolve_unknown_book() -> None:
    with pytest.raises(UnknownBookError):
        resolve_book("Hezekiah")


def test_id_builders_and_parsers() -> None:
    sec = section_id("mark", 1, 1)
    assert sec == "mrk-1-1"
    assert key_idea_id(sec, 3) == "mrk-1-1-k3"
    assert question_id(sec, 12) == "mrk-1-1-q12"
    assert parse_section_id("mrk-16-9").chapter == 16
    parts = parse_item_id("mrk-1-1-q4")
    assert (parts.section, parts.kind, parts.n) == ("mrk-1-1", "q", 4)
    with pytest.raises(ValueError):
        parse_item_id("mrk-1-1-x4")
    with pytest.raises(ValueError):
        key_idea_id("mark-1-1", 1)


# --- refs ---------------------------------------------------------------------------------------


def test_find_refs() -> None:
    text = "See {{ref:1:7}} and {{ref:1:7-8}}."
    assert find_refs(text) == [Ref(1, 7, 7), Ref(1, 7, 8)]
    assert str(Ref(1, 7, 8)) == "{{ref:1:7-8}}"


def test_malformed_refs() -> None:
    assert malformed("{{ref:1}} and {{verse 7}}") == ["{{ref:1}}", "{{verse 7}}"]
    assert malformed("{{ref:1:8-7}}") == ["{{ref:1:8-7}}"]
    assert malformed("fine {{ref:2:3}}") == []


def test_unresolved_refs() -> None:
    sets = {"bsb": {(7, 15), (7, 17)}, "kjv": {(7, 15), (7, 16), (7, 17)}}
    assert unresolved("{{ref:7:15-17}}", sets) == [("bsb", Ref(7, 15, 17))]
    assert unresolved("{{ref:7:15}}", sets) == []


# --- rules --------------------------------------------------------------------------------------

FIXTURES = schema_dir() / "fixtures" / "valid"
BASE: dict[str, Any] = json.loads((FIXTURES / "study-pack-mark-sample.json").read_text())
VERSES = VerseText.model_validate_json((FIXTURES / "verses-bsb-sample.json").read_text())


def violations(
    mutate: Callable[[dict[str, Any]], None], *, with_verses: bool = False
) -> list[Violation]:
    doc = copy.deepcopy(BASE)
    mutate(doc)
    pack = StudyPack.model_validate(doc)
    return cross_field_violations(pack, {"bsb": VERSES} if with_verses else None)


def rules_of(vs: list[Violation]) -> set[int]:
    return {v.rule for v in vs}


def sec(doc: dict[str, Any], i: int = 0) -> dict[str, Any]:
    section: dict[str, Any] = doc["sections"][i]
    return section


def test_valid_pack_is_clean() -> None:
    assert violations(lambda d: None, with_verses=True) == []


def test_rule1_overlap_and_gap() -> None:
    def overlap(d: dict[str, Any]) -> None:
        sec(d, 1)["verseStart"] = 8
        for item in [*sec(d, 1)["keyIdeas"], *sec(d, 1)["questions"]]:
            item["verseStart"] = max(item["verseStart"], 8)

    def gap(d: dict[str, Any]) -> None:
        sec(d)["verseEnd"] = 7
        for item in [*sec(d)["keyIdeas"], *sec(d)["questions"]]:
            item["verseEnd"] = min(item["verseEnd"], 7)

    assert any("overlaps" in v.message for v in violations(overlap))
    assert any("gap" in v.message for v in violations(gap))


def test_rule1_coverage_needs_verses() -> None:
    def drop_second(d: dict[str, Any]) -> None:
        d["sections"] = d["sections"][:1]

    assert violations(drop_second) == []
    vs = violations(drop_second, with_verses=True)
    assert any(v.rule == 1 and "[9, 10, 11]" in v.message for v in vs)


def test_rule2_item_outside_section() -> None:
    def outside(d: dict[str, Any]) -> None:
        sec(d)["keyIdeas"][0]["verseEnd"] = 9

    assert 2 in rules_of(violations(outside))


def test_rule3_ids() -> None:
    def wrong_prefix(d: dict[str, Any]) -> None:
        sec(d)["keyIdeas"][3]["id"] = "mrk-1-9-k4"
        sec(d)["questions"][2]["targets"] = ["mrk-1-9-k4"]

    def duplicate(d: dict[str, Any]) -> None:
        sec(d)["questions"][1]["id"] = "mrk-1-1-q1"

    assert 3 in rules_of(violations(wrong_prefix))
    assert any("duplicate" in v.message for v in violations(duplicate))


def test_rule5_and_rule9_targets() -> None:
    def unknown(d: dict[str, Any]) -> None:
        sec(d)["questions"][1]["targets"] = ["mrk-1-1-k9"]

    def retire_idea(d: dict[str, Any], idea: int) -> None:
        k = sec(d)["keyIdeas"][idea]
        k["status"], k["retiredIn"] = "retired", "1.1.0"

    assert 5 in rules_of(violations(unknown))
    # q4 targets only k3: retiring k3 leaves an active question with only retired targets.
    assert 9 in rules_of(violations(lambda d: retire_idea(d, 2)))
    # q1 targets k1 and k2: retiring k2 alone is a partial retirement (rule 5).
    assert 5 in rules_of(violations(lambda d: retire_idea(d, 1)))


def test_rule6_question_count() -> None:
    """At most 3 active questions, and never more than the active key ideas (no levels)."""

    def four_questions(d: dict[str, Any]) -> None:
        extra = copy.deepcopy(sec(d)["questions"][0])
        extra["id"] = "mrk-1-1-q9"
        sec(d)["questions"].append(extra)

    def two_ideas_three_questions(d: dict[str, Any]) -> None:
        for k in sec(d)["keyIdeas"][2:]:
            k["status"], k["retiredIn"] = "retired", "1.1.0"
        for q in sec(d)["questions"]:
            q["targets"] = ["mrk-1-1-k1"]

    def two_ideas_two_questions(d: dict[str, Any]) -> None:
        two_ideas_three_questions(d)
        q = sec(d)["questions"][2]
        q["status"], q["retiredIn"] = "retired", "1.1.0"

    assert any("at most 3" in v.message for v in violations(four_questions))
    assert any("at most 2 with 2 key ideas" in v.message
               for v in violations(two_ideas_three_questions))  # fmt: skip
    assert violations(two_ideas_two_questions) == []


def test_questions_never_target_background_ideas() -> None:
    def background(d: dict[str, Any]) -> None:
        sec(d)["keyIdeas"][2]["kind"] = "background"  # k3, the only target of q4

    assert any("targets background ideas" in v.message for v in violations(background))


def test_quotes_follow_the_sources() -> None:
    doc = copy.deepcopy(BASE)
    idea = doc["sections"][0]["keyIdeas"][0]
    idea["quotes"] = list(reversed(idea["quotes"]))
    with pytest.raises(ValueError, match="one quote per source"):
        StudyPack.model_validate(doc)


def test_rule7_no_prompt() -> None:
    def no_prompt_with_questions(d: dict[str, Any]) -> None:
        sec(d)["noPrompt"] = True

    def no_prompt_clean(d: dict[str, Any]) -> None:
        sec(d)["noPrompt"] = True
        for q in sec(d)["questions"]:
            q["status"], q["retiredIn"] = "retired", "1.1.0"

    assert 7 in rules_of(violations(no_prompt_with_questions))
    assert violations(no_prompt_clean) == []


def test_rule8_placeholders() -> None:
    def broken(d: dict[str, Any]) -> None:
        sec(d)["context"] = "John appears in {{verse 4}}."

    def unresolvable(d: dict[str, Any]) -> None:
        sec(d)["context"] = "Compare {{ref:7:16}}."

    assert 8 in rules_of(violations(broken))
    assert violations(unresolvable) == []  # needs verse text to judge
    assert 8 in rules_of(violations(unresolvable, with_verses=True))
