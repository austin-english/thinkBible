"""The live publish check: what went live stays, word for word (T066, data-model, FR-024)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from thinkbible_core.models.pack import StudyPack
from thinkbible_pipeline.publish.build import build_pack
from thinkbible_pipeline.publish.publish_check import publish_check


@pytest.fixture
def live(publish_book: Any) -> StudyPack:
    built = build_pack(publish_book.store, publish_book.library, previous=None, live=None,
                       now=datetime(2026, 11, 18, tzinfo=UTC))  # fmt: skip
    assert built is not None
    return built.study


def changed(pack: StudyPack, edit: Callable[[StudyPack], None]) -> StudyPack:
    new = pack.model_copy(deep=True)
    edit(new)
    return new


def test_an_unchanged_or_grown_pack_passes(live: StudyPack) -> None:
    assert publish_check(live, live) == []

    def add(p: StudyPack) -> None:
        idea = p.sections[0].key_ideas[0].model_copy(update={"id": "2jn-1-1-k2"})
        p.sections[0].key_ideas.append(idea)

    assert publish_check(live, changed(live, add)) == []


def test_retire_and_replace_passes(live: StudyPack) -> None:
    def retire_and_replace(p: StudyPack) -> None:
        q = p.sections[0].questions[0]
        q.status, q.retired_in = "retired", "1.1.0"
        p.sections[0].questions.append(
            q.model_copy(
                update={
                    "id": "2jn-1-1-q2",
                    "status": "active",
                    "retired_in": None,
                    "text": "A better question?",
                    "replaces": q.id,
                }
            )
        )

    assert publish_check(live, changed(live, retire_and_replace)) == []


def _drop_section(p: StudyPack) -> None:
    p.sections.pop()


def _move_section(p: StudyPack) -> None:
    p.sections[1].verse_start = 8


def _drop_idea(p: StudyPack) -> None:
    p.sections[0].key_ideas.clear()


def _retitle(p: StudyPack) -> None:
    p.sections[0].key_ideas[0].title = "A new title"


def _rebody(p: StudyPack) -> None:
    p.sections[0].key_ideas[0].body = "A new body."


def _reword(p: StudyPack) -> None:
    p.sections[0].questions[0].text = "A reworded question?"


def _reword_kjv(p: StudyPack) -> None:
    p.sections[0].questions[0].text_by_translation = {"kjv": "A KJV wording?"}


def _reuse(p: StudyPack) -> None:
    p.sections[0].key_ideas[0].kind = "background"


def _bad_replaces(p: StudyPack) -> None:
    p.sections[0].questions[0].replaces = "2jn-1-1-q9"


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        (_drop_section, "section 2jn-1-7 is missing"),
        (_move_section, "section 2jn-1-7 moved from 1:7-13 to 1:8-13"),
        (_drop_idea, "2jn-1-1-k1 is missing (retire it instead)"),
        (_retitle, "2jn-1-1-k1: its published wording changed"),
        (_rebody, "2jn-1-1-k1: its published wording changed"),
        (_reword, "2jn-1-1-q1: its published wording changed"),
        (_reword_kjv, "2jn-1-1-q1: its published wording changed"),
        (_reuse, "2jn-1-1-k1 now names a different item"),
        (_bad_replaces, "2jn-1-1-q1 replaces 2jn-1-1-q9, which isn't retired"),
    ],
)
def test_each_rule_refuses(
    live: StudyPack, edit: Callable[[StudyPack], None], problem: str
) -> None:
    problems = publish_check(live, changed(live, edit))
    assert any(p.startswith(problem) for p in problems), problems


def test_a_retired_item_stays_retired(live: StudyPack) -> None:
    def retire(p: StudyPack) -> None:
        p.sections[0].questions[0].status = "retired"

    retired = changed(live, retire)
    assert any("was retired and is active again" in p for p in publish_check(retired, live))
